// Copyright Poly Hammer. Licensed GPL-3.0 (matches the Character DNA add-on).
using UnrealBuildTool;

public class GroomExporter : ModuleRules
{
    public GroomExporter(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "UnrealEd",          // UCommandlet base; FBX exporter; UExporter::RunAssetExportTask
            "HairStrandsCore",   // UGroomAsset, FHairDescription, FHairDescriptionGroups, HairAttribute::*
            "MeshDescription",   // TAttributesSet / TMeshAttributesConstRef used by HairDescription.h
            "AssetRegistry",     // IAssetRegistry / FARFilter asset discovery
            "Json",              // groom_manifest.json writer
            "JsonUtilities",
        });
    }
}
