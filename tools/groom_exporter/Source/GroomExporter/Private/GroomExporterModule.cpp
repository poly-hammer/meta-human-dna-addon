// Copyright Poly Hammer. Licensed GPL-3.0 (matches the Character DNA add-on).
#include "Modules/ModuleManager.h"

// The commandlet is auto-discovered by reflection, so the module itself does no
// work beyond existing to be loaded; an empty IModuleInterface is enough.
class FGroomExporterModule : public IModuleInterface
{
public:
    virtual void StartupModule() override {}
    virtual void ShutdownModule() override {}
};

IMPLEMENT_MODULE(FGroomExporterModule, GroomExporter);
