import argparse
import getpass
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pywintypes
import win32cred
import win32ras


# ===================== SETTINGS =====================

CONNECTION_NAME = "Broadband Connection"

# Check every five minutes.
CHECK_INTERVAL_SECONDS = 5 * 60

MAX_CONNECT_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 60

# Credential name inside Windows Credential Manager.
CREDENTIAL_TARGET = f"PPPoE-Watchdog:{CONNECTION_NAME}"

# ====================================================


SCRIPT_FOLDER = Path(__file__).resolve().parent
LOG_FOLDER = SCRIPT_FOLDER / "logs"
LOG_FILE = LOG_FOLDER / "pppoe_watchdog.log"


def configure_logging() -> logging.Logger:
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("PPPoEWatchdog")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


logger = configure_logging()


def save_credentials() -> None:
    """Save PPPoE credentials in Windows Credential Manager."""

    print(f"Saving credentials for: {CONNECTION_NAME}")

    username = input("PPPoE username: ").strip()
    password = getpass.getpass("PPPoE password: ")

    if not username:
        raise ValueError("The PPPoE username cannot be empty.")

    if not password:
        raise ValueError("The PPPoE password cannot be empty.")

    credential = {
        "Type": win32cred.CRED_TYPE_GENERIC,
        "TargetName": CREDENTIAL_TARGET,
        "UserName": username,
        "CredentialBlob": password,
        "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
        "Comment": "PPPoE Watchdog credentials",
    }

    win32cred.CredWrite(credential, 0)

    print()
    print("Credentials saved successfully in Windows Credential Manager.")
    print("The password is not stored inside the Python file.")


def load_credentials() -> tuple[str, str]:
    """Load credentials from Windows Credential Manager."""

    try:
        credential = win32cred.CredRead(
            CREDENTIAL_TARGET,
            win32cred.CRED_TYPE_GENERIC,
            0,
        )

    except pywintypes.error as error:
        raise RuntimeError(
            "PPPoE credentials were not found. Run:\n"
            f'python "{Path(__file__)}" --setup'
        ) from error

    username = credential.get("UserName", "").strip()
    password_blob = credential.get("CredentialBlob", b"")

    if isinstance(password_blob, bytes):
        password = password_blob.decode(
            "utf-16-le",
            errors="strict",
        ).rstrip("\x00")
    else:
        password = str(password_blob)

    if not username or not password:
        raise RuntimeError(
            "The saved PPPoE credential is incomplete. "
            "Run the script again with --setup."
        )

    return username, password


def get_active_connections() -> list[str]:
    """Return names of currently active Windows RAS connections."""

    connections = win32ras.EnumConnections()

    return [
        str(connection[1])
        for connection in connections
        if len(connection) > 1
    ]


def is_pppoe_connected() -> bool:
    """Check whether our PPPoE connection is active."""

    target = CONNECTION_NAME.casefold()

    return any(
        name.casefold() == target
        for name in get_active_connections()
    )


def get_ras_error(error_code: int) -> str:
    """Convert a RAS error code into readable text."""

    try:
        return win32ras.GetErrorString(error_code).strip()
    except Exception:
        return f"Windows RAS error {error_code}"


def connect_pppoe_once() -> bool:
    """Perform one PPPoE connection attempt."""

    username, password = load_credentials()

    # RASDIALPARAMS order:
    # entry name, phone number, callback number,
    # username, password and domain.
    dial_parameters = (
        CONNECTION_NAME,
        "",
        "",
        username,
        password,
        "",
    )

    connection_handle = 0

    try:
        connection_handle, error_code = win32ras.Dial(
            None,
            None,
            dial_parameters,
            None,
        )

        if error_code != 0:
            logger.warning(
                "[FAILED] RAS error %d: %s",
                error_code,
                get_ras_error(error_code),
            )

            if (
                connection_handle
                and win32ras.IsHandleValid(connection_handle)
            ):
                try:
                    win32ras.HangUp(connection_handle)
                except Exception:
                    pass

            return False

        if not win32ras.IsHandleValid(connection_handle):
            logger.warning(
                "[FAILED] Windows did not return a valid RAS handle."
            )
            return False

        time.sleep(2)

        if is_pppoe_connected():
            logger.info(
                "[RESTORED] PPPoE connection is connected again."
            )
            return True

        logger.warning(
            "[VERIFY FAILED] Windows completed the dial request, "
            "but the connection is not listed as active."
        )
        return False

    except pywintypes.error as error:
        logger.error(
            "[RAS ERROR] Windows RAS API failure: %s",
            error,
        )
        return False

    except Exception:
        logger.exception(
            "[ERROR] Unexpected error during connection."
        )
        return False


def reconnect_pppoe() -> bool:
    """Attempt to restore the PPPoE connection."""

    for attempt in range(1, MAX_CONNECT_ATTEMPTS + 1):
        logger.info(
            "[CONNECT] Attempt %d/%d for '%s'.",
            attempt,
            MAX_CONNECT_ATTEMPTS,
            CONNECTION_NAME,
        )

        if connect_pppoe_once():
            return True

        if attempt < MAX_CONNECT_ATTEMPTS:
            logger.info(
                "[RETRY] Waiting %d seconds.",
                RETRY_DELAY_SECONDS,
            )
            time.sleep(RETRY_DELAY_SECONDS)

    logger.error(
        "[GIVEUP] Failed after %d attempts. "
        "The watchdog will try again during the next check.",
        MAX_CONNECT_ATTEMPTS,
    )

    return False


def check_connection() -> bool:
    """Check the PPPoE connection and restore it if necessary."""

    logger.info(
        "[CHECK] Checking '%s'.",
        CONNECTION_NAME,
    )

    try:
        if is_pppoe_connected():
            logger.info(
                "[OK] PPPoE connection is connected."
            )
            return True

        logger.warning(
            "[DOWN] PPPoE connection is disconnected."
        )

        return reconnect_pppoe()

    except Exception:
        logger.exception(
            "[ERROR] Unexpected watchdog error."
        )
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lightweight Windows PPPoE watchdog."
    )

    parser.add_argument(
        "--setup",
        action="store_true",
        help="Save or update PPPoE credentials.",
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one check and then exit.",
    )

    arguments = parser.parse_args()

    if arguments.setup:
        save_credentials()
        return

    logger.info("[START] PPPoE watchdog started.")
    logger.info(
        "[CONFIG] Connection: %s",
        CONNECTION_NAME,
    )
    logger.info(
        "[CONFIG] Check interval: %d seconds.",
        CHECK_INTERVAL_SECONDS,
    )
    logger.info(
        "[CONFIG] Log file: %s",
        LOG_FILE,
    )

    if arguments.once:
        check_connection()
        return

    try:
        while True:
            check_connection()
            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logger.info(
            "[STOP] Watchdog stopped by the user."
        )

    except Exception:
        logger.exception(
            "[FATAL] Watchdog stopped unexpectedly."
        )
        raise


if __name__ == "__main__":
    main()