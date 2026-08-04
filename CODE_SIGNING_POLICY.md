# Code Signing Policy

Release builds of ModbusLens (the `ModbusLens.exe` published on the
[GitHub Releases page](https://github.com/professoroptimusprime/ModScope/releases))
are code-signed free of charge by the [SignPath Foundation](https://signpath.org/)
using a certificate provided through [SignPath.io](https://signpath.io/).

## Attribution

Free code signing provided by [SignPath.io](https://signpath.io/), certificate by
[SignPath Foundation](https://signpath.org/).

## Team

ModbusLens is currently maintained by a single developer, who holds all three
SignPath roles for this project:

| Role | Person |
|---|---|
| Author | professoroptimusprime |
| Reviewer | professoroptimusprime |
| Approver | professoroptimusprime |

Every tagged release is built from source via the project's GitHub Actions
workflow (`.github/workflows/build.yml`) and manually approved before signing.
Multi-factor authentication is enabled on the GitHub account and SignPath
account used to control this project and submit builds for signing.

## Privacy and system changes

ModbusLens does not collect, transmit, or store any telemetry, usage data, or
personal data. All Modbus/network communication it performs (device
discovery, register reads/writes) is initiated directly by the user against
devices on their own network and stays local to their machine.

ModbusLens does not modify Windows system configuration, the registry, or
network adapter settings. The "IP Configuration" view is read-only and only
displays the machine's existing network adapters.

## Installation and removal

ModbusLens is distributed as a single portable `.exe` with no installer and
no bundled dependencies added to the system. To remove it, delete the `.exe`
file; no other files or settings are left behind outside the application's
own local config directory (if used).
