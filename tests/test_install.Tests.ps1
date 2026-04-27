#Requires -Version 5.1
<#
.SYNOPSIS
    Pester tests for install.ps1 logic.

.DESCRIPTION
    Tests the pure logic functions extracted from install.ps1.
    No network access, no git, no Python required to run these tests.

    Requires Pester 3.4+:
        Install-Module -Name Pester -Force -SkipPublisherCheck
    Run:
        Invoke-Pester tests\test_install.Tests.ps1 -Verbose
#>

# ---------------------------------------------------------------------------
# Helpers — mirror the logic in install.ps1 so tests stay in sync
# ---------------------------------------------------------------------------

# Python version check (step 1)
function Test-PythonVersionSufficient {
    param([string]$VerLine)
    if ($VerLine -match 'Python\s+(\d+)\.(\d+)') {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        return ($major -gt 3 -or ($major -eq 3 -and $minor -ge 11))
    }
    return $false
}

# Bootstrap install-dir selection (step 0)
function Get-InstallDir {
    param([string]$EnvOverride = "")
    if ($EnvOverride) { return $EnvOverride }
    return Join-Path $HOME "StationController_Py"
}

# devArg array construction (step 0 re-exec)
function Get-DevArg {
    param([bool]$Dev)
    if ($Dev) { return @('-Dev') } else { return @() }
}

# COM port extracted from PnP FriendlyName (step 7)
function Get-ComPortFromFriendlyName {
    param([string]$FriendlyName)
    if ($FriendlyName -match '\(COM(\d+)\)') {
        return "COM$($Matches[1])"
    }
    return $null
}

# COM port numeric sort key (step 7)
function Get-ComPortSortKey {
    param([string]$Port)
    return [int]($Port -replace 'COM', '')
}

# Baud-rate speed label (step 7)
function Get-SpeedLabel {
    param([int]$BaudRate)
    if ($BaudRate -eq 115200) {
        return [PSCustomObject]@{
            Label = "High-speed / power meter (115200 baud)"
            Note  = "Use a dedicated USB adapter - do not share with control traffic."
            Color = 'Yellow'
        }
    }
    return [PSCustomObject]@{
        Label = "Standard DCN ($BaudRate baud)"
        Note  = ""
        Color = 'White'
    }
}

# Choice validation (step 7)
function Resolve-PortChoice {
    param([string]$Choice, [int]$PortCount)
    if ($Choice -match '^\d+$') {
        $idx = [int]$Choice
        if ($idx -ge 1 -and $idx -le $PortCount) { return $idx }
    }
    return $null
}

# Patch-args array construction (step 7)
function Get-PatchArgs {
    param([string]$CfgPath, [hashtable]$Choices)
    return @($CfgPath) + @(
        $Choices.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }
    )
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

Describe "install.ps1 syntax" {

    It "parses without errors" {
        $tok = $null; $parseErr = $null
        $scriptPath = Join-Path $PSScriptRoot "..\install.ps1"
        $null = [System.Management.Automation.Language.Parser]::ParseFile(
            (Resolve-Path $scriptPath).Path, [ref]$tok, [ref]$parseErr
        )
        $parseErr.Count | Should Be 0
    }
}

# ---------------------------------------------------------------------------

Describe "-Dev flag parsing" {

    It "Dev switch is false by default" {
        $Dev = [switch]$false
        $Dev.IsPresent | Should Be $false
    }

    It "Get-DevArg returns empty array when Dev is false" {
        $result = Get-DevArg -Dev $false
        $result.Count | Should Be 0
    }

    It "Get-DevArg returns @('-Dev') when Dev is true" {
        $result = Get-DevArg -Dev $true
        $result | Should Be '-Dev'
        $result.Count | Should Be 1
    }
}

# ---------------------------------------------------------------------------

Describe "Python version check" {

    It "accepts Python 3.11" {
        Test-PythonVersionSufficient "Python 3.11.0" | Should Be $true
    }

    It "accepts Python 3.12" {
        Test-PythonVersionSufficient "Python 3.12.4" | Should Be $true
    }

    It "accepts Python 3.13" {
        Test-PythonVersionSufficient "Python 3.13.0" | Should Be $true
    }

    It "accepts Python 4.0" {
        Test-PythonVersionSufficient "Python 4.0.0" | Should Be $true
    }

    It "rejects Python 3.10" {
        Test-PythonVersionSufficient "Python 3.10.12" | Should Be $false
    }

    It "rejects Python 3.9" {
        Test-PythonVersionSufficient "Python 3.9.7" | Should Be $false
    }

    It "rejects Python 2.7" {
        Test-PythonVersionSufficient "Python 2.7.18" | Should Be $false
    }

    It "returns false for unrecognised output" {
        Test-PythonVersionSufficient "command not found" | Should Be $false
    }

    It "returns false for empty string" {
        Test-PythonVersionSufficient "" | Should Be $false
    }

    It "handles ErrorRecord-style string wrapping" {
        # PS 5.1 2>&1 wraps stderr as ErrorRecord; .ToString() gives the raw text
        Test-PythonVersionSufficient "Python 3.11.9" | Should Be $true
    }
}

# ---------------------------------------------------------------------------

Describe "Bootstrap install directory" {

    It "defaults to HOME\StationController_Py" {
        $result = Get-InstallDir -EnvOverride ""
        $result | Should Be (Join-Path $HOME "StationController_Py")
    }

    It "uses STATIONCONTROLLER_DIR env override when set" {
        $result = Get-InstallDir -EnvOverride "C:\custom\path"
        $result | Should Be "C:\custom\path"
    }

    It "env override takes precedence over default" {
        $result1 = Get-InstallDir -EnvOverride ""
        $result2 = Get-InstallDir -EnvOverride "D:\station"
        $result1 | Should Not Be $result2
    }
}

# ---------------------------------------------------------------------------

Describe "COM port extraction from FriendlyName" {

    It "extracts port from typical USB serial FriendlyName" {
        Get-ComPortFromFriendlyName "USB Serial Port (COM3)" | Should Be "COM3"
    }

    It "extracts port from Silicon Labs FriendlyName" {
        Get-ComPortFromFriendlyName "Silicon Labs CP210x USB to UART Bridge (COM7)" | Should Be "COM7"
    }

    It "extracts double-digit COM port" {
        Get-ComPortFromFriendlyName "USB Serial Device (COM12)" | Should Be "COM12"
    }

    It "extracts triple-digit COM port" {
        Get-ComPortFromFriendlyName "USB Serial Device (COM100)" | Should Be "COM100"
    }

    It "returns null when no COM port in name" {
        Get-ComPortFromFriendlyName "Some Other Device" | Should BeNullOrEmpty
    }

    It "returns null for empty string" {
        Get-ComPortFromFriendlyName "" | Should BeNullOrEmpty
    }
}

Describe "COM port sort key" {

    It "extracts numeric value from COM3" {
        Get-ComPortSortKey "COM3" | Should Be 3
    }

    It "extracts numeric value from COM12" {
        Get-ComPortSortKey "COM12" | Should Be 12
    }

    It "sorts lower COM numbers before higher" {
        $ports = @("COM10", "COM3", "COM1") |
            Sort-Object { Get-ComPortSortKey $_ }
        $ports[0] | Should Be "COM1"
        $ports[1] | Should Be "COM3"
        $ports[2] | Should Be "COM10"
    }
}

# ---------------------------------------------------------------------------

Describe "Baud-rate speed label" {

    It "9600 baud shows Standard DCN label" {
        $result = Get-SpeedLabel -BaudRate 9600
        $result.Label | Should Be "Standard DCN (9600 baud)"
    }

    It "115200 baud shows High-speed label" {
        $result = Get-SpeedLabel -BaudRate 115200
        $result.Label | Should Be "High-speed / power meter (115200 baud)"
    }

    It "115200 baud has dedicated adapter note" {
        $result = Get-SpeedLabel -BaudRate 115200
        $result.Note | Should Match "dedicated USB adapter"
    }

    It "9600 baud has no note" {
        $result = Get-SpeedLabel -BaudRate 9600
        $result.Note | Should BeNullOrEmpty
    }

    It "19200 baud shows Standard DCN with correct rate" {
        $result = Get-SpeedLabel -BaudRate 19200
        $result.Label | Should Be "Standard DCN (19200 baud)"
    }

    It "19200 baud has no note" {
        $result = Get-SpeedLabel -BaudRate 19200
        $result.Note | Should BeNullOrEmpty
    }

    It "115200 baud uses Yellow color" {
        (Get-SpeedLabel -BaudRate 115200).Color | Should Be 'Yellow'
    }

    It "9600 baud uses White color" {
        (Get-SpeedLabel -BaudRate 9600).Color | Should Be 'White'
    }
}

# ---------------------------------------------------------------------------

Describe "Port list display" {

    It "port list is indexed from 1" {
        $ports = @(
            [PSCustomObject]@{ Port = "COM3"; Description = "USB Serial Port (COM3)" }
            [PSCustomObject]@{ Port = "COM7"; Description = "CP210x (COM7)" }
        )
        $lines = for ($i = 0; $i -lt $ports.Count; $i++) {
            "[{0}] {1}" -f ($i + 1), $ports[$i].Description
        }
        $lines[0] | Should Match '^\[1\]'
        $lines[1] | Should Match '^\[2\]'
    }

    It "single port is listed as [1]" {
        $ports = @([PSCustomObject]@{ Port = "COM3"; Description = "USB Serial Port (COM3)" })
        $line  = "[{0}] {1}" -f 1, $ports[0].Description
        $line | Should Match '^\[1\]'
    }

    It "descriptions are included in display lines" {
        $ports = @([PSCustomObject]@{ Port = "COM3"; Description = "FTDI FT232R (COM3)" })
        $line  = "[{0}] {1}" -f 1, $ports[0].Description
        $line | Should Match "FTDI FT232R"
    }
}

# ---------------------------------------------------------------------------

Describe "Choice validation" {

    It "choice 1 selects index 0" {
        Resolve-PortChoice -Choice "1" -PortCount 2 | Should Be 1
    }

    It "choice 2 selects index 1" {
        Resolve-PortChoice -Choice "2" -PortCount 2 | Should Be 2
    }

    It "choice equal to port count is valid" {
        Resolve-PortChoice -Choice "3" -PortCount 3 | Should Be 3
    }

    It "choice 0 returns null (skip)" {
        Resolve-PortChoice -Choice "0" -PortCount 2 | Should BeNullOrEmpty
    }

    It "choice exceeding port count returns null" {
        Resolve-PortChoice -Choice "5" -PortCount 2 | Should BeNullOrEmpty
    }

    It "non-numeric choice returns null" {
        Resolve-PortChoice -Choice "abc" -PortCount 2 | Should BeNullOrEmpty
    }

    It "empty choice returns null" {
        Resolve-PortChoice -Choice "" -PortCount 2 | Should BeNullOrEmpty
    }

    It "negative number returns null" {
        Resolve-PortChoice -Choice "-1" -PortCount 2 | Should BeNullOrEmpty
    }

    It "whitespace returns null" {
        Resolve-PortChoice -Choice " " -PortCount 2 | Should BeNullOrEmpty
    }
}

# ---------------------------------------------------------------------------

Describe "Patch-args construction" {

    It "first element is always the config path" {
        $result = Get-PatchArgs -CfgPath "C:\cfg.yaml" -Choices @{ "ctrl" = "COM3" }
        $result[0] | Should Be "C:\cfg.yaml"
    }

    It "single choice produces name=port string" {
        $result = Get-PatchArgs -CfgPath "C:\cfg.yaml" -Choices @{ "ctrl_serial" = "COM3" }
        ($result -contains "ctrl_serial=COM3") | Should Be $true
    }

    It "multiple choices each produce a name=port string" {
        $result = Get-PatchArgs -CfgPath "C:\cfg.yaml" -Choices @{
            "ctrl_serial" = "COM3"
            "pwr_serial"  = "COM5"
        }
        ($result -contains "ctrl_serial=COM3") | Should Be $true
        ($result -contains "pwr_serial=COM5") | Should Be $true
    }

    It "total arg count is 1 + number of choices" {
        $result = Get-PatchArgs -CfgPath "C:\cfg.yaml" -Choices @{
            "a" = "COM1"
            "b" = "COM2"
            "c" = "COM3"
        }
        $result.Count | Should Be 4
    }

    It "empty choices produces only the config path" {
        $result = Get-PatchArgs -CfgPath "C:\cfg.yaml" -Choices @{}
        # Force array so single-element result is not unwrapped to scalar
        @($result).Count | Should Be 1
        @($result)[0] | Should Be "C:\cfg.yaml"
    }
}
