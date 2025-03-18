#!/usr/bin/python
from __future__ import print_function
import requests
import json
from smartcard.CardType import AnyCardType
from smartcard.CardRequest import CardRequest
from smartcard.Exceptions import CardRequestTimeoutException
import tkinter as tk
from tkinter import ttk
import time


def send_apdu(cardservice, apdu_str):
    """
    convert the hex string to a list of bytes, then send the APDU command to the card,
    and return the full response as a string
    """
    apdu = [int(apdu_str[i : i + 2], 16) for i in range(0, len(apdu_str), 2)]
    response, sw1, sw2 = cardservice.connection.transmit(apdu)
    full_response = "".join(
        "{:02X}".format(x) for x in response
    ) + "{:02X}{:02X}".format(sw1, sw2)
    return full_response


def show_json_ui(data):
    """
    this function creates an interactive UI to display specific parts of the JSON data.

    Expected JSON structure (only the shown fields are used):

    {
        "titleList": {
            "cardName": "..."
        },
        "balance": {
            "desfireSerial": "...",
            "initAppDate": "...",
            "finishAppDate": "...",
            "groupName": "...",
            "groupShortName": "...",
            "groupId": "...",
            "initGroupDate": "...",
            "finishGroupDate": "...",
            "profiles": [
                {
                    "profileId": "...",
                    "profileName": "...",
                    "initProfileDate": "...",
                    "finishProfileDate": "..."
                },
                ...
            ]
        },
        other fields (don't seem quite necessary at this stage) ..
    }
    """
    root = tk.Tk()
    root.title("Madrid Card")

    title_frame = ttk.Frame(root, padding="10")
    title_frame.pack(fill="x")
    card_name = data.get("titleList", {}).get("cardName", "Unknown Card Name")
    title_label = ttk.Label(title_frame, text=card_name, font=("Helvetica", 16, "bold"))
    title_label.pack()

    # Balance Section: Display key balance values
    balance_frame = ttk.LabelFrame(root, text="Balance", padding="10")
    balance_frame.pack(fill="x", padx=10, pady=5)
    desfire_serial = data.get("balance", {}).get("desfireSerial", "N/A")
    init_app_date = data.get("balance", {}).get("initAppDate", "N/A")
    finish_app_date = data.get("balance", {}).get("finishAppDate", "N/A")
    ttk.Label(balance_frame, text=f"Card Serial: {desfire_serial}").pack(anchor="w")
    ttk.Label(balance_frame, text=f"Start Contract: {init_app_date}").pack(anchor="w")
    ttk.Label(balance_frame, text=f"Expiry: {finish_app_date}").pack(anchor="w")

    # Group Section: Display group-related information
    group_frame = ttk.LabelFrame(root, text="Group", padding="10")
    group_frame.pack(fill="x", padx=10, pady=5)
    group_name = data.get("balance", {}).get("groupName", "N/A")
    group_short_name = data.get("balance", {}).get("groupShortName", "N/A")
    group_id = data.get("balance", {}).get("groupId", "N/A")
    init_group_date = data.get("balance", {}).get("initGroupDate", "N/A")
    finish_group_date = data.get("balance", {}).get("finishGroupDate", "N/A")
    ttk.Label(group_frame, text=f"Group Name: {group_name}").pack(anchor="w")
    ttk.Label(group_frame, text=f"Group Short Name: {group_short_name}").pack(
        anchor="w"
    )
    ttk.Label(group_frame, text=f"Group ID: {group_id}").pack(anchor="w")
    ttk.Label(group_frame, text=f"Init Group Date: {init_group_date}").pack(anchor="w")
    ttk.Label(group_frame, text=f"Finish Group Date: {finish_group_date}").pack(
        anchor="w"
    )

    # Profiles Section: Display each profile in balance->profiles
    profiles_frame = ttk.LabelFrame(root, text="Profiles", padding="10")
    profiles_frame.pack(fill="x", padx=10, pady=5)
    profiles = data.get("balance", {}).get("profiles", [])
    if profiles:
        for idx, profile in enumerate(profiles):
            prof_frame = ttk.Frame(profiles_frame, padding="5")
            prof_frame.pack(fill="x", pady=2)
            profile_id = profile.get("profileId", "N/A")
            profile_name = profile.get("profileName", "N/A")
            init_profile_date = profile.get("initProfileDate", "N/A")
            finish_profile_date = profile.get("finishProfileDate", "N/A")
            ttk.Label(prof_frame, text=f"Profile {idx + 1}:").pack(anchor="w")
            ttk.Label(prof_frame, text=f"  ID: {profile_id}").pack(anchor="w", padx=20)
            ttk.Label(prof_frame, text=f"  Name: {profile_name}").pack(
                anchor="w", padx=20
            )
            ttk.Label(prof_frame, text=f"  Init Date: {init_profile_date}").pack(
                anchor="w", padx=20
            )
            ttk.Label(prof_frame, text=f"  Finish Date: {finish_profile_date}").pack(
                anchor="w", padx=20
            )
    else:
        ttk.Label(profiles_frame, text="No profiles available").pack()

    root.mainloop()


def main():
    # initialize HTTP connection
    session = requests.Session()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "okhttp/4.12.0",
    }  # use okhttp because that's what the app uses
    session.headers.update(headers)

    # initiate a connection with the server.
    init_url = "https://latsecu.comunidad.madrid/middlelat/midd/device/init/conn"
    init_data = {
        "language": "en",
        "timezone": "Europe/Madrid",
    }
    init_response = session.post(init_url, data=json.dumps(init_data))

    # base payload for card reading requests
    card_reading_url = (
        "https://latsecu.comunidad.madrid/middlelat/device/front/CardReading"
    )
    payload_base = {
        "titleList": "COMMON_PLUS_SUP",
        "salePoint": "010201000005",
        "updateCard": True,
        "commandType": "WRAPPED",
        "opInspection": False,
    }

    # Initial POST: get first set of CAPDU commands (without RAPDU)
    print("Sending initial card reading request...")
    response = session.post(card_reading_url, data=json.dumps(payload_base))
    try:
        json_response = response.json()
    except json.JSONDecodeError:
        print("Failed to decode initial card reading response as JSON.")
        return

    # Wait for card insertion (only once) before processing CAPDU commands
    card_type = AnyCardType()
    try:
        print("Insert a card within 10 seconds...")
        card_request = CardRequest(timeout=10, cardType=card_type)
        card_service = card_request.waitforcard()
        card_service.connection.connect()
        print("connecting to card..")
        time.sleep(2)
    except CardRequestTimeoutException:
        print("Timeout: No card inserted within 10 seconds.")
        return

    iteration = 0
    max_iterations = 5
    while json_response.get("capdu") and iteration < max_iterations:
        capdu_commands = json_response["capdu"]
        print("Iteration", iteration, "received CAPDU commands:", capdu_commands)
        rapdu_responses = []
        for cmd in capdu_commands:
            print("Sending CAPDU command:", cmd)
            rapdu = send_apdu(card_service, cmd)
            print("Received RAPDU:", rapdu)
            rapdu_responses.append(rapdu)

        payload = payload_base.copy()
        payload["rapdu"] = rapdu_responses
        print("Sending POST with RAPDU responses:", rapdu_responses)
        response = session.post(card_reading_url, data=json.dumps(payload))
        try:
            json_response = response.json()
        except json.JSONDecodeError:
            print("Failed to decode card reading response")
            break
        iteration += 1

    show_json_ui(json_response)


if __name__ == "__main__":
    main()
