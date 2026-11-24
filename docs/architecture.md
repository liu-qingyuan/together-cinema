# Historical deployment design: private snapshot → distributable project

Recorded on **2026-11-23**, before the first Alpha source release. “Current” below means the private snapshot at design time; “Target” means the planned distributable deployment, not a comparison of today's code. Preserved as a migration record; use the [current code map](code-map.md) for navigation and [deployment guide](deployment.md) for operation.

Scope at the time: a new deployment Interface, original playback Module preserved. No production changes.

## Current architecture
```mermaid
flowchart LR
  Person["Operator"] --> Manual["Site-specific shell/config"]
  Manual --> App["Watch application"]
  App --> Store["Media directory"]
  App --> Worker["Extractor"]
  Converter["FFmpeg worker"] --> Store
```
## Target architecture
```mermaid
flowchart LR
  Person["Operator"] --> Install["install.sh"]
  Install --> Compose["Docker Compose"]
  Compose --> App["Watch application"]
  Compose --> Converter["FFmpeg worker"]
  Compose --> Network["Optional extractor"]
  Compose --> TLS["Optional HTTPS and access gate"]
  App --> Store["Named data volume"]
  Converter --> Store
  TLS --> App
```
## Current sequence
```mermaid
sequenceDiagram
  participant O as Operator
  participant C as Private configuration
  participant A as Application
  O->>C: Copy host-specific settings
  O->>A: Start existing images manually
  A-->>O: Health response
```
## Target sequence
```mermaid
sequenceDiagram
  participant O as Operator
  participant I as Installer
  participant E as Local env
  participant D as Compose
  O->>I: Run install.sh
  I->>D: Check engine and Compose
  I->>E: Generate missing secrets atomically
  I->>D: Validate, build and up with wait
  D-->>I: Healthy or explicit failure
  I-->>O: Local URL or configured HTTPS URL
```
## Current lifecycle
```mermaid
stateDiagram-v2
  [*] --> MissingConfig
  MissingConfig --> Configured: manual host setup
  Configured --> Running: manual container start
  Running --> Stopped: manual stop
  Stopped --> Running: manual restart
```
## Target lifecycle
```mermaid
stateDiagram-v2
  [*] --> CheckDependencies
  CheckDependencies --> Failed: Docker unavailable
  CheckDependencies --> Initialize: dependencies ready
  Initialize --> Validate: preserve or generate env
  Validate --> Failed: invalid config
  Validate --> Starting: valid config
  Starting --> Failed: build or health failure
  Starting --> Running: healthy
  Running --> StoppedDataRetained: uninstall default
  StoppedDataRetained --> Running: install again
  StoppedDataRetained --> DataRemoved: explicit purge and yes
```
## Current ownership
```mermaid
classDiagram
  class PrivateConfig {
    hostPorts
    externalDomain
    existingImageNames
  }
  class Application {
    create_app()
  }
  PrivateConfig --> Application
```
## Target ownership
Shell roles below are Interface responsibilities, not newly introduced Python classes.
```mermaid
classDiagram
  class Installer {
    main(args)
    random_hex()
    set_value(key,value)
  }
  class Env {
    signingKey
    sitePassword
    profiles
  }
  class Compose {
    watch
    converter
    extractor
    https
  }
  class Application {
    create_app()
  }
  Installer --> Env
  Installer --> Compose
  Compose --> Application
```
