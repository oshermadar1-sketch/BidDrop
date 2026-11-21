# End-to-end flows (Maestro)

These flows drive the real Android app on the emulator.

1. Install Maestro once: https://maestro.mobile.dev/getting-started/installing-maestro
   (needs Java 17; on Windows run it from Git Bash or WSL).
2. Start the emulator and install the latest preview APK.
3. Run a flow:

    maestro test -e EMAIL=biddrop.sender.demo@example.com -e PASSWORD=... .maestro/login.yaml
    maestro test .maestro/create_request.yaml

`create_request.yaml` expects the demo couriers (`python scripts/demo_data.py add`) so a match is found.
