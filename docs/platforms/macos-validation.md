# What we tested on Mac

Incoooming passed native automated checks on Intel and Apple Silicon Macs on September 5, 2026
(UTC). **Use Chrome for CSV imports on Mac.** Safari's interface was tested; Safari file selection
and CSV import remain unverified.

The tested code is commit [`59e43d3`](https://github.com/ehwwpk/incoooming-unofficial-desk/commit/59e43d3a19de206e1b1972c8f851adaf9cbe08e1).
All six [Mac jobs](https://github.com/ehwwpk/incoooming-unofficial-desk/actions/runs/33944378523)
and all three [Windows jobs](https://github.com/ehwwpk/incoooming-unofficial-desk/actions/runs/33944378552)
passed. The final documentation and screenshots describe that tested application code.

## Platform coverage

| Native Mac | Python versions tested | Core tests in each job | Python coverage |
| --- | --- | --- | --- |
| Apple Silicon, macOS 15.7.9 | 3.12.10, 3.13.15, 3.14.7 | 811 passed | 92.26% |
| Intel, macOS 15.7.9 | 3.12.10, 3.13.15, 3.14.7 | 811 passed | 92.26% |

Every Mac job checked lint, strict types, dependency advisories, common security mistakes,
installation from a fresh wheel, packaged migrations/assets, and the real setup/start commands.
Windows checked the same Python versions: 803 tests passed in each job, with eight POSIX-only
tests skipped and 92.26% coverage. Both platforms reported two test warnings, with no failures.

The native browser and Keychain checks ran on Python 3.14.7:

| Machine | Recorded macOS | Chrome | Safari | Runner image |
| --- | --- | --- | --- | --- |
| Apple Silicon | 15.7.9 | 152.0.7977.65 | 26.6.1 | 20260829.0321.1 |
| Intel | 15.7.9 | 151.0.7922.174 | 26.6 | 20260824.0482.1 |

These were real browser applications running on hosted Macs. Chrome ran with a visible window
and its normal sandbox. Screenshots and result metadata were downloaded and inspected.

## What worked

- **Setup and restarts:** fresh and repeated setup, folders with spaces, commands run from
  outside the project folder, preserved settings, relative data paths and explicit overrides.
  Duplicate launches and unrelated occupied ports were rejected without touching the other
  listener. Control+C stopped the owned server, and restarting worked.
- **Saved login storage:** the native macOS Keychain backend saved, loaded in a fresh process,
  updated, and deleted unique dummy credentials. Repeated deletion correctly reported absence.
  Unit and integration tests separately cover denied, locked, unavailable, and corrupt storage.
- **The interface in both browsers:** the source chooser, demo Desk, four Results comparison
  lines, period changes, keyboard inspection of dates, modeled risk, and the exact put-roll
  handoff to Radar. Screenshots showed no horizontal overflow at the recorded viewport sizes.
- **CSV in Chrome:** real files were selected from disk, previewed, and imported. The browser
  rejected a file over 10 MiB before making an upload request. Reselecting files or editing the
  book name invalidated the old preview. Changing a file on disk after review still imported
  the exact reviewed bytes: two positions, two activity rows, and $19,375 of imported position
  value. The imported book did not gain an invented historical benchmark chart.

## Limits of this evidence

SafariDriver could select filenames but could not read their contents. Fresh single-file and
multiple-file attempts failed before upload, and the native system log recorded file sandbox
extension/read denials. The [diagnostic run](https://github.com/ehwwpk/incoooming-unofficial-desk/actions/runs/33943433362)
preserves this result. Selenium also has
[expected failures for Safari upload tests](https://github.com/SeleniumHQ/selenium/commit/71bc491039bbd688e0a6c1407597aded33dc1471).
This does not prove that ordinary manual Safari uploads fail, but it prevents us from calling
them verified. Chrome is the supported Mac CSV path; Safari's passing check covers the interface.

No real Schwab account was authorized or synced on a Mac during these checks. OAuth responses
were mocked and Keychain entries were disposable dummy tokens. Developer approval, account
permissions, market-data access, and interactive Keychain permission dialogs remain outside
this evidence. There is no claim of an App Store app, notarized installer, iPhone/iPad support,
all macOS versions, or testing on physical Retina displays. Recorded device pixel ratio was 1;
Safari's viewport was 1425 by 948 and Chrome's was 1425 by 541.

## Preserved evidence

The workflow saves platform, launcher, Keychain, Safari, and Chrome JSON records plus screenshots
and server logs. Downloadable artifacts expire after 14 days; this report preserves the measured
coverage. The two independently inspected browser artifact ZIPs have these SHA-256 hashes:

| Architecture | Artifact ID | SHA-256 |
| --- | --- | --- |
| Apple Silicon | 9962912025 | `61ef890ba7ee6f6c52374344c4831fdadacc4b8dc9e5a5281f7114956e75fb37` |
| Intel | 9962923656 | `0e30cf20a8e414f40d1523c290b45bc563acd11bbd4f3caee52479b14e7077a4` |

The README screenshots are untouched fictional Safari captures from the earlier `eae5393`
run; its application source matches the tested code above. The later commit changes only the
Chrome test's scrolling/click helper.
