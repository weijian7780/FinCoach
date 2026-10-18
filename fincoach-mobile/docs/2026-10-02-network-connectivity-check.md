# FinCoach network connectivity check — 2 October 2026

All times below are Malaysia time (UTC+8). Target: `https://api.chisquaredv10.dpdns.org`.

## Live results

- Docker container: running and healthy; local `/health` HTTP 200.
- Windows Cloudflared service: running.
- Public `/health` and `/ready`: HTTP 200; OCR and embeddings ready.
- Globalping HTTPS GET `/health`: six probes in five countries, all HTTP 200 and `{"status":"ok"}`. This tests public DNS/HTTPS/tunnel/origin reachability; it does not authenticate or generate an AI answer.

| Country | City | Probe network | HTTP |
| --- | --- | --- | --- |
| Malaysia | Cyberjaya | BRANDON MAXWELL LOOI, AS219206 | 200 |
| Malaysia | Kuala Lumpur | IP ServerOne Solutions, AS45352 | 200 |
| Singapore | Singapore | Oracle, AS31898 | 200 |
| Japan | Tokyo | Oracle, AS31898 | 200 |
| Germany | Falkenstein | Hetzner Online, AS24940 | 200 |
| USA | Buffalo | HostPapa, AS36352 | 200 |

Raw public measurement: https://api.globalping.io/v1/measurements/2eEyQLomMMIip5JFw00021F6B
Saved request/results: `superpowers/plans/2026-10-02-network-health-measurement.json` and `superpowers/plans/2026-10-02-network-health-results.json`.

## Phone evidence and limits

- The user confirmed that switching between Wi-Fi and mobile data was available and reported the current test succeeds. ADB had no connected phone, so this remains user-reported; the exact per-network AI answer was not independently inspected.
- Earlier in this chat, version 32 loaded Coach on mobile data with Automatic Private DNS after force-stop/reopen, corroborated by successful Coach history GET responses.
- Network switching alone has not been shown to cause the current failure. These checks do not guarantee access through every carrier, restricted Wi-Fi network, or future interruption.

## Confirmed laptop availability issue

Windows logs show:

| Time | Event |
| --- | --- |
| 18:33:16 | Entered Modern Standby, reason Idle Timeout |
| 18:33:34 | Network disconnected |
| 18:43:28 | Exited Modern Standby; network connected |
| 18:43:59 | Entered Modern Standby again |
| 18:44:18 | Network disconnected again |

The 18:42 timestamp in the earlier phone screenshot falls inside the first standby/disconnected interval. This is strong evidence that the unattended host was unavailable then. The screenshot's NXDOMAIN error independently indicates a phone/browser DNS problem; host sleep does not establish the cause of that DNS response.

Current active power plan: Turbo. Sleep after 300 seconds on AC or 180 seconds on battery. Closing the lid triggers sleep on AC and battery. Battery hibernation after 3600 seconds; AC hibernation disabled.

## Hosting action

Keep the laptop plugged in, connected to the internet, and its lid open while hosting. Set plugged-in sleep to Never, for example:

```powershell
powercfg /change standby-timeout-ac 0
```

This changes the active plan's AC sleep timeout only. To restore the observed five-minute AC timeout:

```powershell
powercfg /change standby-timeout-ac 5
```

No Windows power settings were changed during this read-only check. No new APK or backend deployment was performed.

Microsoft Modern Standby reference: https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/modern-standby
