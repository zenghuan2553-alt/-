$ErrorActionPreference = 'Stop'
$testDir = Join-Path $PSScriptRoot 'test-audio'
New-Item -ItemType Directory -Path $testDir -Force | Out-Null
$testVoice = New-Object -ComObject SAPI.SpVoice
$englishVoice = @($testVoice.GetVoices() | Where-Object { $_.GetDescription() -match 'English' })
if ($englishVoice.Count -eq 0) { throw 'No Windows English voice is installed.' }
$testVoice.Voice = $englishVoice[0]
$sentences = @(
    'Hello, welcome to this video.',
    'Please open the file and click the start button.',
    'We are learning how to use this software.',
    'The model runs on your computer without an internet connection.',
    'You can move the subtitles to the bottom of the screen.',
    'Stop the video before changing the audio device.',
    'Save your work before closing the window.',
    'Now connect the VAE decoder.',
    'Choose a sampler and load the checkpoint.',
    'This program translates English speech into Chinese.'
)
for ($testIndex = 0; $testIndex -lt $sentences.Count; $testIndex++) {
    $testStream = New-Object -ComObject SAPI.SpFileStream
    $testStream.Open((Join-Path $testDir ('{0:D2}.wav' -f $testIndex)), 3, $false)
    $testVoice.AudioOutputStream = $testStream
    $testVoice.Speak($sentences[$testIndex]) | Out-Null
    $testStream.Close()
}
$sentences | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $testDir 'sentences.json') -Encoding UTF8
Write-Output 'Generated 10 synthetic English samples locally; no microphone recording.'
