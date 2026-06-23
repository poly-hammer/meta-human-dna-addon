// Copyright Poly Hammer. Licensed GPL-3.0 (matches the Character DNA add-on).
//
// Reads MetaHuman UGroomAsset strand geometry and writes it in the Character DNA
// add-on's flat groom format: one ".cdgr" binary per groom (highest-detail render
// strands) plus a "groom_manifest.json". The add-on's groom_io package reads these.
//
// The binary layout MUST stay in sync with:
//   src/addons/character_dna/groom_io/io.py
// Positions are written in Unreal's space (centimetres, Z-up, left-handed); the
// add-on converts to Blender's space on import (see curves_builder.py).

#include "GroomExportCommandlet.h"
#include UE_INLINE_GENERATED_CPP_BY_NAME(GroomExportCommandlet)

#include "GroomAsset.h"
#include "GroomAssetRendering.h"
#include "HairStrandsDatas.h"

#include "AssetRegistry/ARFilter.h"
#include "AssetRegistry/AssetData.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/IAssetRegistry.h"

#include "Engine/StaticMesh.h"
#include "AssetExportTask.h"
#include "Exporters/Exporter.h"
#include "Exporters/FbxExportOption.h"

#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

DEFINE_LOG_CATEGORY_STATIC(LogGroomExport, Log, All);

// ---- .cdgr format constants (keep in sync with groom_io/io.py) -----------------
static const uint32 GroomFormatVersion = 1;
static const uint32 FlagWidths = 1u << 0;
static const uint32 FlagRootUV = 1u << 1;
static const uint32 FlagGroupID = 1u << 2;
static const uint32 FlagGuide = 1u << 3;

UGroomExportCommandlet::UGroomExportCommandlet(const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer)
{
}

// ---- little-endian byte appenders (Unreal target platforms are little-endian) --
static void AppendBytes(TArray<uint8>& Out, const void* Data, int32 NumBytes)
{
    const int32 Start = Out.AddUninitialized(NumBytes);
    FMemory::Memcpy(Out.GetData() + Start, Data, NumBytes);
}

template <typename T>
static void AppendPOD(TArray<uint8>& Out, T Value)
{
    AppendBytes(Out, &Value, sizeof(T));
}

static bool WriteGroomBinary(
    const FString& FilePath,
    const TArray<int32>& CurveOffsets, // size N + 1
    const TArray<FVector3f>& Positions, // size P
    const TArray<float>& Widths, // size 0 or P
    const TArray<FVector2f>& RootUV, // size 0 or N
    const TArray<int32>& GroupID, // size 0 or N
    const TArray<int32>& Guide) // size 0 or N
{
    const uint32 CurveCount = CurveOffsets.Num() > 0 ? (uint32)(CurveOffsets.Num() - 1) : 0;
    const uint32 PointCount = (uint32)Positions.Num();

    uint32 Flags = 0;
    if (Widths.Num() == (int32)PointCount && PointCount > 0) Flags |= FlagWidths;
    if (RootUV.Num() == (int32)CurveCount && CurveCount > 0) Flags |= FlagRootUV;
    if (GroupID.Num() == (int32)CurveCount && CurveCount > 0) Flags |= FlagGroupID;
    if (Guide.Num() == (int32)CurveCount && CurveCount > 0) Flags |= FlagGuide;

    TArray<uint8> Buffer;
    const uint8 Magic[4] = {'C', 'D', 'G', 'R'};
    AppendBytes(Buffer, Magic, 4);
    AppendPOD<uint32>(Buffer, GroomFormatVersion);
    AppendPOD<uint32>(Buffer, CurveCount);
    AppendPOD<uint32>(Buffer, PointCount);
    AppendPOD<uint32>(Buffer, Flags);
    AppendPOD<uint32>(Buffer, 0u); // reserved

    for (int32 Offset : CurveOffsets)
    {
        AppendPOD<int32>(Buffer, Offset);
    }
    for (const FVector3f& Position : Positions)
    {
        AppendPOD<float>(Buffer, Position.X);
        AppendPOD<float>(Buffer, Position.Y);
        AppendPOD<float>(Buffer, Position.Z);
    }
    if (Flags & FlagWidths)
    {
        for (float Width : Widths)
        {
            AppendPOD<float>(Buffer, Width);
        }
    }
    if (Flags & FlagRootUV)
    {
        for (const FVector2f& UV : RootUV)
        {
            AppendPOD<float>(Buffer, UV.X);
            AppendPOD<float>(Buffer, UV.Y);
        }
    }
    if (Flags & FlagGroupID)
    {
        for (int32 Value : GroupID)
        {
            AppendPOD<int32>(Buffer, Value);
        }
    }
    if (Flags & FlagGuide)
    {
        for (int32 Value : Guide)
        {
            AppendPOD<int32>(Buffer, Value);
        }
    }

    if (!FFileHelper::SaveArrayToFile(Buffer, *FilePath))
    {
        UE_LOG(LogGroomExport, Error, TEXT("Failed to write '%s'."), *FilePath);
        return false;
    }
    return true;
}

#if WITH_EDITOR
// Compute absolute per-point widths (diameter, centimetres) for a group.
//
// The decoded raw datas store a per-point radius normalized to [0..1]; the
// absolute scale comes from the group's render HairWidth setting. This is robust
// (per-point, per-group, no flat-description index matching) and gives widths in
// the expected ~0.01 cm range. Width is secondary to curve geometry, so when the
// data is unavailable the array is left empty and Blender uses a default radius.
static TArray<float> ComputeWidths(UGroomAsset* Groom, int32 GroupIndex, const FHairStrandsRawDatas& Strands)
{
    TArray<float> Widths;
    const TArray<float>& Radius = Strands.StrandsPoints.PointsRadius; // normalized [0..1]
    if (Radius.Num() == 0)
    {
        return Widths;
    }

    float HairWidth = 0.0f; // diameter, centimetres
    const TArray<FHairGroupsRendering>& Rendering = Groom->GetHairGroupsRendering();
    if (Rendering.IsValidIndex(GroupIndex))
    {
        HairWidth = Rendering[GroupIndex].GeometrySettings.HairWidth;
    }
    if (HairWidth <= 0.0f)
    {
        HairWidth = 0.01f; // ~0.1 mm fallback when the setting is unset
    }

    Widths.SetNumUninitialized(Radius.Num());
    for (int32 Index = 0; Index < Radius.Num(); ++Index)
    {
        Widths[Index] = Radius[Index] * HairWidth;
    }
    return Widths;
}

static int32 ExportGroom(
    UGroomAsset* Groom, const FString& OutDir, bool bExportWidths, TArray<TSharedPtr<FJsonValue>>& GroomEntries)
{
    if (!Groom->CanRebuildFromDescription())
    {
        UE_LOG(LogGroomExport, Warning, TEXT("Groom '%s' has no rebuildable HairDescription; skipping."), *Groom->GetName());
        return 0;
    }

    const FHairDescriptionGroups& Groups = Groom->GetHairDescriptionGroups();
    if (Groups.HairGroups.Num() == 0)
    {
        UE_LOG(LogGroomExport, Warning, TEXT("Groom '%s' has no description groups; skipping."), *Groom->GetName());
        return 0;
    }

    const bool bSingleGroup = Groups.HairGroups.Num() == 1;
    int32 Written = 0;

    for (int32 GroupIndex = 0; GroupIndex < Groups.HairGroups.Num(); ++GroupIndex)
    {
        const FHairDescriptionGroup& Group = Groups.HairGroups[GroupIndex];
        const FHairStrandsRawDatas& Strands = Group.Strands; // render strands, not guides
        const int32 N = (int32)Strands.GetNumCurves();
        const int32 P = (int32)Strands.GetNumPoints();
        if (N == 0 || P == 0)
        {
            continue;
        }

        // Offset-index topology, built from the per-curve point counts.
        TArray<int32> Offsets;
        Offsets.Reserve(N + 1);
        Offsets.Add(0);
        int32 Accumulated = 0;
        for (int32 Curve = 0; Curve < N; ++Curve)
        {
            Accumulated += (int32)Strands.StrandsCurves.CurvesCount[Curve];
            Offsets.Add(Accumulated);
        }

        const TArray<FVector3f>& Positions = Strands.StrandsPoints.PointsPosition;

        TArray<FVector2f> RootUV;
        if (Strands.StrandsCurves.CurvesRootUV.Num() == N)
        {
            RootUV = Strands.StrandsCurves.CurvesRootUV;
        }

        TArray<int32> GroupIDs;
        GroupIDs.Init(Group.Info.GroupID, N);

        TArray<float> Widths;
        if (bExportWidths)
        {
            Widths = ComputeWidths(Groom, GroupIndex, Strands);
        }

        const FString EntryName = bSingleGroup ? Groom->GetName() : FString::Printf(TEXT("%s_Group%d"), *Groom->GetName(), GroupIndex);
        const FString FileName = EntryName + TEXT(".cdgr");
        const FString FilePath = FPaths::Combine(OutDir, FileName);

        if (WriteGroomBinary(FilePath, Offsets, Positions, Widths, RootUV, GroupIDs, /*Guide*/ TArray<int32>()))
        {
            TSharedPtr<FJsonObject> Entry = MakeShared<FJsonObject>();
            Entry->SetStringField(TEXT("name"), EntryName);
            Entry->SetStringField(TEXT("kind"), TEXT("strands"));
            Entry->SetStringField(TEXT("geometry"), FileName);
            Entry->SetNumberField(TEXT("group_id"), Group.Info.GroupID);
            Entry->SetNumberField(TEXT("lod"), 0);
            Entry->SetNumberField(TEXT("curve_count"), N);
            Entry->SetNumberField(TEXT("point_count"), P);
            Entry->SetNumberField(TEXT("guide_count"), Group.Info.NumGuides);
            Entry->SetStringField(TEXT("surface"), TEXT("head"));
            GroomEntries.Add(MakeShared<FJsonValueObject>(Entry));
            ++Written;
            UE_LOG(LogGroomExport, Display, TEXT("Exported groom '%s' (%d curves, %d points) -> %s"), *EntryName, N, P, *FileName);
        }
    }
    return Written;
}
#endif // WITH_EDITOR

static void ExportCards(UStaticMesh* Mesh, const FString& OutDir, TArray<TSharedPtr<FJsonValue>>& GroomEntries)
{
    const FString Name = Mesh->GetName();
    // Only hair-cards meshes, and only the highest-detail (LOD0) variant.
    if (!Name.Contains(TEXT("Cards")))
    {
        return;
    }
    if (Name.Contains(TEXT("_LOD")) && !Name.Contains(TEXT("_LOD0")))
    {
        return;
    }

    const FString FileName = Name + TEXT(".fbx");
    UAssetExportTask* Task = NewObject<UAssetExportTask>();
    Task->Object = Mesh;
    Task->Filename = FPaths::Combine(OutDir, FileName);
    Task->bAutomated = true;
    Task->bPrompt = false;
    Task->bReplaceIdentical = true;
    UFbxExportOption* Options = NewObject<UFbxExportOption>();
    Options->bASCII = false;
    Task->Options = Options;

    if (UExporter::RunAssetExportTask(Task))
    {
        TSharedPtr<FJsonObject> Entry = MakeShared<FJsonObject>();
        Entry->SetStringField(TEXT("name"), Name);
        Entry->SetStringField(TEXT("kind"), TEXT("cards"));
        Entry->SetStringField(TEXT("geometry"), FileName);
        Entry->SetNumberField(TEXT("lod"), 0);
        GroomEntries.Add(MakeShared<FJsonValueObject>(Entry));
        UE_LOG(LogGroomExport, Display, TEXT("Exported cards '%s' -> %s"), *Name, *FileName);
    }
    else
    {
        UE_LOG(LogGroomExport, Warning, TEXT("Failed to export cards FBX for '%s'."), *Name);
    }
}

int32 UGroomExportCommandlet::Main(const FString& Params)
{
    TArray<FString> Tokens;
    TArray<FString> Switches;
    TMap<FString, FString> ParamVals;
    UCommandlet::ParseCommandLine(*Params, Tokens, Switches, ParamVals);

    FString OutDir;
    if (!FParse::Value(*Params, TEXT("OutDir="), OutDir) || OutDir.IsEmpty())
    {
        UE_LOG(LogGroomExport, Error, TEXT("Missing required -OutDir=<folder>."));
        return 1;
    }
    FString ContentPath = TEXT("/Game");
    FParse::Value(*Params, TEXT("ContentPath="), ContentPath);
    const bool bExportCards = Switches.Contains(TEXT("Cards"));
    const bool bExportWidths = Switches.Contains(TEXT("Widths"));

    OutDir = FPaths::ConvertRelativePathToFull(OutDir);
    IFileManager::Get().MakeDirectory(*OutDir, true);
    UE_LOG(LogGroomExport, Display, TEXT("Groom export: ContentPath=%s OutDir=%s Cards=%d Widths=%d"), *ContentPath, *OutDir, bExportCards, bExportWidths);

    IAssetRegistry& AssetRegistry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
    AssetRegistry.SearchAllAssets(true);

    FARFilter Filter;
    Filter.bRecursivePaths = true;
    Filter.bRecursiveClasses = true;
    Filter.PackagePaths.Add(FName(*ContentPath));
    Filter.ClassPaths.Add(UGroomAsset::StaticClass()->GetClassPathName());
    if (bExportCards)
    {
        Filter.ClassPaths.Add(UStaticMesh::StaticClass()->GetClassPathName());
    }

    TArray<FAssetData> AssetList;
    AssetRegistry.GetAssets(Filter, AssetList);
    UE_LOG(LogGroomExport, Display, TEXT("Found %d candidate assets under %s."), AssetList.Num(), *ContentPath);

    TArray<TSharedPtr<FJsonValue>> GroomEntries;
    int32 NumGrooms = 0;

    for (const FAssetData& AssetData : AssetList)
    {
        if (UGroomAsset* Groom = Cast<UGroomAsset>(AssetData.GetAsset()))
        {
#if WITH_EDITOR
            NumGrooms += ExportGroom(Groom, OutDir, bExportWidths, GroomEntries);
#endif
        }
        else if (bExportCards)
        {
            if (UStaticMesh* Mesh = Cast<UStaticMesh>(AssetData.GetAsset()))
            {
                ExportCards(Mesh, OutDir, GroomEntries);
            }
        }
    }

    // Write the manifest the add-on reads.
    TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetStringField(TEXT("format"), TEXT("character_dna_groom"));
    Root->SetNumberField(TEXT("version"), 1);
    Root->SetStringField(TEXT("source"), ContentPath);
    TSharedPtr<FJsonObject> Space = MakeShared<FJsonObject>();
    Space->SetStringField(TEXT("units"), TEXT("cm"));
    Space->SetStringField(TEXT("up_axis"), TEXT("Z"));
    Space->SetStringField(TEXT("handedness"), TEXT("left"));
    Root->SetObjectField(TEXT("space"), Space);
    Root->SetArrayField(TEXT("grooms"), GroomEntries);

    FString ManifestText;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ManifestText);
    FJsonSerializer::Serialize(Root.ToSharedRef(), Writer);
    const FString ManifestPath = FPaths::Combine(OutDir, TEXT("groom_manifest.json"));
    if (!FFileHelper::SaveStringToFile(ManifestText, *ManifestPath))
    {
        UE_LOG(LogGroomExport, Error, TEXT("Failed to write manifest '%s'."), *ManifestPath);
        return 1;
    }

    UE_LOG(LogGroomExport, Display, TEXT("Done. Wrote %d groom(s) and %d manifest entries to %s"), NumGrooms, GroomEntries.Num(), *OutDir);
    return 0;
}
