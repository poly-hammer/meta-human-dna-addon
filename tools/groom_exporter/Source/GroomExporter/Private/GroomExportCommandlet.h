// Copyright Poly Hammer. Licensed GPL-3.0 (matches the Character DNA add-on).
#pragma once

#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "GroomExportCommandlet.generated.h"

/**
 * Headless commandlet that reads MetaHuman UGroomAsset strand geometry and
 * writes it in the Character DNA add-on's flat groom format.
 *
 * Run with:
 *   UnrealEditor-Cmd <Project>.uproject -run=GroomExport \
 *       -OutDir=<folder> [-ContentPath=/Game/MetaHumans] [-Cards] [-Widths]
 *
 * (UE strips the leading "U" and the "Commandlet" suffix, so the class
 * UGroomExportCommandlet is invoked as -run=GroomExport.)
 */
UCLASS()
class UGroomExportCommandlet : public UCommandlet
{
    GENERATED_UCLASS_BODY()

public:
    virtual int32 Main(const FString& Params) override;
};
