$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$outDir = Join-Path $root "dist"
$zipPath = Join-Path $outDir "tiny-macro-arch-wayland-build-kit.zip"

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

$items = @(
    ".gitignore",
    "README.md",
    "pyproject.toml",
    "src",
    "tests",
    "packaging",
    "scripts/build_arch_wayland.sh"
)

$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("tiny-macro-build-kit-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temp | Out-Null

try {
    foreach ($item in $items) {
        $source = Join-Path $root $item
        $target = Join-Path $temp $item
        if (Test-Path -PathType Container -LiteralPath $source) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $source -Destination $target -Recurse
        } else {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $source -Destination $target
        }
    }
    Compress-Archive -Path (Join-Path $temp "*") -DestinationPath $zipPath
    Write-Host "Created $zipPath"
} finally {
    if (Test-Path -LiteralPath $temp) {
        Remove-Item -LiteralPath $temp -Recurse -Force
    }
}
