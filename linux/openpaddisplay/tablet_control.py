"""Live display controls over the USB connection, independent of the video stream."""
import base64
import json
import re
import subprocess


def control_tablet(command, *, visible=None, test_id=None, motion=False):
    args = ["adb", "-d", "shell", "am", "broadcast", "--receiver-foreground",
            "-a", "org.openpaddisplay.CONTROL_DIAGNOSTICS", "-p", "org.openpaddisplay",
            "--es", "command", command]
    if visible is not None:
        args.extend(("--ez", "visible", str(bool(visible)).lower()))
    if test_id is not None:
        args.extend(("--es", "test_id", test_id))
    if motion:
        args.extend(("--ez", "motion", "true"))
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Não foi possível comunicar com o tablet por USB.") from exc
    match = re.search(r'\bOPAD:([A-Za-z0-9+/=]+)', result.stdout)
    if match is None:
        raise RuntimeError("Abre o OpenPadDisplay no tablet e confirma que o APK é 0.4.1 ou posterior.")
    try:
        response = json.loads(base64.b64decode(match[1], validate=True))
        if not isinstance(response, dict) or type(response.get("visible")) is not bool:
            raise ValueError("Invalid response")
        return response
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("O tablet devolveu uma resposta de diagnóstico inválida.") from exc
