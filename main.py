# --- START OF FILE HeXakills_v3_ScheduledSafari_FullyScoped.py ---

import subprocess
import asyncio
import re
import random
import os
import logging
from collections import deque
from enum import Enum
import schedule # For scheduling
import time     # For scheduler loop

from telethon import TelegramClient, events
from telethon.errors import MessageIdInvalidError, FloodWaitError
from telethon.tl.types import InputPeerUser

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
api_id = '25695711' # Keep your credentials secure
api_hash = 'f20065cc26d4a31bf0efc0b44edaffa9' # Keep your credentials secure
session_file_name = 'your_sessssssion.session' # Use a descriptive session file name

# --- Bot Configuration ---
POKEZONE_BOT_ID = 572621020 # The integer ID of the PokeZone bot
YOUR_NOTIFICATION_CHAT_ID = -1002245132909 # Your chat/group ID for notifications
SCHEDULE_TIME = "14:55" # Time to run daily, e.g., "18:00" for 6 PM. Ensure HH:MM format.

# --- Dynamic State Variables (managed per cycle) ---
class BotPhase(Enum):
    IDLE = 0
    ATTEMPTING_SAFARI_ENTRY = 1
    IN_SAFARI = 2
    TRANSITIONING_TO_NORMAL = 3
    IN_NORMAL_HUNT = 4
    COMPLETED_CYCLE = 5

current_bot_phase = BotPhase.IDLE
safari_active_this_cycle = False # True if currently in the Safari part of the daily run
is_currently_in_safari_zone = False # True if bot is confirmed inside Safari Zone
safari_balls_remaining = 0

# --- Normal Mode Configuration (used when safari_active_this_cycle is False) ---
HEALTH_THRESHOLD_PERCENT = 150
INITIAL_LOW_LEVEL_HP = 60

# --- Delays ---
SAFARI_HUNT_COMMAND_INTERVAL = random.uniform(2.5, 4.0)
SAFARI_ACTION_DELAY = lambda: random.uniform(0.7, 1.3)
NORMAL_TURN_DELAY = lambda: random.uniform(2.5, 4.0)
NORMAL_ACTION_DELAY = lambda: random.uniform(1.0, 2.0)
BATTLE_INIT_DELAY = lambda: random.uniform(0.5, 1.5)

# --- Pokemon Lists (for Normal Mode) ---
repeat_ball_poks = [
    "Zapdos", "Mewtwo", "Lugia", "Ho-Oh", "Kyogre", "Groudon", "Rayquaza", "Jirachi", "Deoxys",
    "Dialga", "Palkia", "Regigigas", "Giratina", "Shaymin", "Arceus", "Victini", "Cobalion",
    "Terrakion", "Virizion", "Reshiram", "Zekrom", "Landorus", "Kyurem", "Keldeo", "Genesect",
    "Xerneas", "Yveltal", "Zygarde", "Diancie", "Hoopa", "Cosmog", "Cosmoem", "Buzzwole",
    "Pheromosa", "Kartana", "Necrozma", "Magearna", "Marshadow", "Blacephalon", "Zeraora",
    "Zacian", "Zamazenta", "Eternatus", "Kubfu", "Spectrier", "Glastrier", "Regieleki", "Regidrago",
    "Aerodactyl", "Lopunny", "Charizard", "Gallade", "Manectric", "Sceptile", "Salamence",
    "Pidgeot", "Venusaur", "Blastoise", "Beedrill", "Alakazam", "Gyarados", "Audino",
    "Abomasnow", "Steelix", "Ampharos", "Lucario", "Greninja","✨"
]
regular_ball_poks = [
    "Slowpoke", "Slowbro", "Slowking", "Ponyta", "Rapidash", "Flapple", "Appletun",
    "Magikarp", "Darumaka", "Darmanitan", "Drakloak", "Duraludon", "Rotom", "Snorlax", "Overqwil",
    "Munchlax", "Kleavor", "Fennekin", "Delphox", "Braixen", "Axew", "Fraxure", "Haxorus",
    "Floette", "Flabebe", "Porygon", "Porygon2", "Mankey", "Primeape", "Dratini", "Shellder",
    "Gible", "Gabite", "Dragonair", "Vikavolt", "Wimpod", "Golisopod", "Buneary", "Hawlucha",
    "Jolteon", "Dwebble", "Crustle", "Starly", "Staravia", "Staraptor", "Vaporeon", "Cyndaquil",
    "Quilava", "Typhlosion", "Totodile", "Croconaw", "Feraligatr", "Espeon", "Slakoth",
    "Vigoroth", "Slaking", "Lotad", "Lombre", "Ludicolo", "Electrike", "Manectric", "Monferno",
    "Infernape", "Chimchar", "Sirfetch'd", "Tepig", "Pignite", "Emboar", "Spiritomb", "Skorupi",
    "Drapion", "Drilbur", "Excadrill", "Shelmet", "Accelgor", "Tyrunt", "Tyrantrum", "Sylveon",
    "Litleo", "Pyroar", "Phantump", "Trevenant", "Popplio", "Brionne", "Primarina", "Dracozolt",
    "Dracovish", "Sneasler", "Mareanie", "Toxapex", "Arctozolt", "Arctovish", "Chewtle",
    "Drednaw"
]

# --- State Variables ---
low_lvl_pokemon_normal_mode = False # Specific to normal mode

# --- Client Initialization (Global, connect/disconnect per cycle) ---
client = TelegramClient(session_file_name, api_id, api_hash)
bot_entity = None # This will be the InputPeerUser for the bot
periodic_hunt_task = None # To manage the asyncio task

# --- Helper Function ---
def calculate_health_percentage(max_hp, current_hp):
    if max_hp <= 0: return 0
    current_hp = max(0, min(current_hp, max_hp))
    return round((current_hp / max_hp) * 100)

async def transition_to_normal_hunting_mode(reason="Safari ended"):
    global safari_active_this_cycle, is_currently_in_safari_zone, current_bot_phase
    if safari_active_this_cycle: # Ensure we were in Safari mode
        logger.info(f"{reason}. Transitioning to Normal Hunting Mode.")
        safari_active_this_cycle = False
        is_currently_in_safari_zone = False
        current_bot_phase = BotPhase.IN_NORMAL_HUNT
        await asyncio.sleep(NORMAL_TURN_DELAY())
        await send_hunt_command() # Initiate normal hunting

# --- Event Handlers ---
# CRITICAL: All event handlers below are now scoped with `chats=POKEZONE_BOT_ID`
# and `from_users=POKEZONE_BOT_ID` to ensure they only react to messages
# from the specified bot in the Direct Message chat with it.

@client.on(events.NewMessage(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"Daily hunt limit reached", re.IGNORECASE)))
async def dailyLimitReached(event):
    global current_bot_phase
    if current_bot_phase == BotPhase.IN_NORMAL_HUNT:
        logger.warning("Overall daily hunt limit reached (during Normal Hunt). Current cycle complete.")
        current_bot_phase = BotPhase.COMPLETED_CYCLE
        if client.is_connected():
            await client.disconnect()
    elif current_bot_phase == BotPhase.IN_SAFARI:
        logger.info("Safari mode active: 'Daily hunt limit reached' msg received. This might be Safari's own limit. Let Safari-specific handler manage.")
    else:
        logger.debug(f"Daily hunt limit message received, but bot phase is {current_bot_phase.name}. Action depends on context.")

@client.on(events.NewMessage(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"✨ Shiny Pokémon found!", re.IGNORECASE)))
async def shinyFound(event):
    logger.info("✨ Shiny Pokémon found! Notifying and DISCONNECTING (ending current cycle).")
    try:
        await client.send_message(YOUR_NOTIFICATION_CHAT_ID, "🚨 SHINY FOUND! Check Telegram NOW! 🚨")
    except Exception as e:
        logger.error(f"Failed to send shiny notification: {e}")
    if client.is_connected():
        await client.disconnect()

# --- Safari Zone Specific Handlers ---
@client.on(events.NewMessage(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"Welcome to the (.*?) Safari Zone!", re.IGNORECASE)))
async def safari_entry_confirmation(event):
    global is_currently_in_safari_zone, current_bot_phase, safari_balls_remaining
    if safari_active_this_cycle and current_bot_phase == BotPhase.ATTEMPTING_SAFARI_ENTRY:
        zone_name = event.pattern_match.group(1)
        logger.info(f"Successfully entered the {zone_name} Safari Zone!")
        is_currently_in_safari_zone = True
        current_bot_phase = BotPhase.IN_SAFARI
        ball_match = re.search(r"You will be given (\d+) Safari Balls", event.raw_text, re.IGNORECASE)
        if ball_match:
            safari_balls_remaining = int(ball_match.group(1))
            logger.info(f"Initial Safari Balls: {safari_balls_remaining}")
        logger.info("Sending initial /hunt for Safari.")
        await asyncio.sleep(SAFARI_ACTION_DELAY())
        await send_hunt_command()

@client.on(events.NewMessage(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"The Safari Game has finished and you were kicked out", re.IGNORECASE)))
@client.on(events.MessageEdited(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"The Safari Game has finished and you were kicked out", re.IGNORECASE)))
async def safari_game_finished_kicked_out(event):
    if safari_active_this_cycle and is_currently_in_safari_zone:
        await transition_to_normal_hunting_mode("Safari Game finished (kicked out)")

@client.on(events.NewMessage(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"You have run out of Safari Balls!", re.IGNORECASE)))
@client.on(events.MessageEdited(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"You have run out of Safari Balls!", re.IGNORECASE)))
async def safari_out_of_balls(event):
    if safari_active_this_cycle and is_currently_in_safari_zone:
        await transition_to_normal_hunting_mode("Ran out of Safari Balls")

@client.on(events.NewMessage(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"You have reached the /hunt limit for the Safari Zone!", re.IGNORECASE)))
@client.on(events.MessageEdited(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"You have reached the /hunt limit for the Safari Zone!", re.IGNORECASE)))
async def safari_hunt_limit_in_zone_reached(event):
    if safari_active_this_cycle and is_currently_in_safari_zone:
        await transition_to_normal_hunting_mode("Reached /hunt limit for Safari Zone")

# --- Modified Encounter Handler ---
@client.on(events.NewMessage(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"A wild (.*?) \(Lv\. \d+\) has appeared", re.IGNORECASE)))
async def handle_encounter(event):
    global low_lvl_pokemon_normal_mode, safari_balls_remaining
    pok_name_match = re.search(r"A wild (.*?) \(Lv\. \d+\) has appeared", event.raw_text, re.IGNORECASE)
    if not pok_name_match:
        return
    pok_name = pok_name_match.group(1).strip().rstrip('☆').strip()
    logger.info(f"Encountered: {pok_name} (Phase: {current_bot_phase.name})")
    await asyncio.sleep(BATTLE_INIT_DELAY())
    try:
        if safari_active_this_cycle and is_currently_in_safari_zone:
            ball_match = re.search(r"Safari Balls remaining: (\d+)", event.raw_text, re.IGNORECASE)
            if ball_match:
                safari_balls_remaining = int(ball_match.group(1))
                logger.info(f"Safari Balls remaining: {safari_balls_remaining}")
            if event.buttons and event.buttons[0] and any(b.text == "Engage" for b in event.buttons[0]):
                await event.click(text="Engage"); logger.info(f"Safari: Clicked 'Engage' for {pok_name}.")
            else: logger.warning(f"Safari: 'Engage' button not found for {pok_name}. Msg: {event.raw_text}")
        elif not safari_active_this_cycle and current_bot_phase == BotPhase.IN_NORMAL_HUNT:
            low_lvl_pokemon_normal_mode = False
            if pok_name in regular_ball_poks or pok_name in repeat_ball_poks:
                if event.buttons and event.buttons[0] and any(b.text == "Battle" for b in event.buttons[0]):
                    await event.click(text="Battle"); logger.info(f"Normal: Clicked 'Battle' for {pok_name}.")
                else: logger.warning(f"Normal: 'Battle' button not found for {pok_name}.")
            else:
                logger.info(f"Normal: {pok_name} not on lists. Sending /hunt.")
                await asyncio.sleep(NORMAL_TURN_DELAY()); await send_hunt_command()
    except FloodWaitError as fwe: logger.warning(f"Flood wait ({fwe.seconds}s) on initial click. Waiting."); await asyncio.sleep(fwe.seconds + 2)
    except Exception as e: logger.exception(f"Error in handle_encounter for {pok_name}: {e}")

@client.on(events.NewMessage(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"Wild .*?Safari Balls: \d+", re.IGNORECASE)))
@client.on(events.MessageEdited(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"Wild .*?Safari Balls: \d+", re.IGNORECASE)))
async def handle_safari_throw_prompt(event):
    global safari_balls_remaining
    if not (safari_active_this_cycle and is_currently_in_safari_zone): return
    pok_name_match = re.search(r"Wild (.*?) \[(?:.*?)\] - Lv\.", event.raw_text)
    pok_name = pok_name_match.group(1).strip() if pok_name_match else "Unknown Pokemon"
    ball_match = re.search(r"Safari Balls: (\d+)", event.raw_text, re.IGNORECASE)
    if ball_match: safari_balls_remaining = int(ball_match.group(1))
    logger.info(f"Safari: {pok_name}. Balls: {safari_balls_remaining}. Attempting throw.")
    if safari_balls_remaining <= 0: logger.warning("Safari: Detected 0 Safari Balls. Game might end soon."); return
    try:
        if event.buttons and event.buttons[0] and any(b.text == "Throw ball" for b in event.buttons[0]):
            await asyncio.sleep(SAFARI_ACTION_DELAY())
            await event.click(text="Throw ball"); logger.info(f"Safari: Clicked 'Throw ball' for {pok_name}.")
        else: logger.warning(f"Safari: 'Throw ball' button not found for {pok_name}. Buttons: {event.buttons}")
    except FloodWaitError as fwe: logger.warning(f"Flood wait ({fwe.seconds}s) clicking 'Throw ball'. Waiting."); await asyncio.sleep(fwe.seconds + 2)
    except Exception as e: logger.exception(f"Safari: Unexpected error clicking 'Throw ball' for {pok_name}: {e}")

# --- Normal Mode Battle Logic ---
@client.on(events.NewMessage(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"Battle begins!", re.IGNORECASE)))
async def battle_start_normal_mode(event):
    if safari_active_this_cycle or current_bot_phase != BotPhase.IN_NORMAL_HUNT: return
    logger.info("Normal Mode: Battle has started. Analyzing...")
    await process_battle_state_normal_mode(event)

@client.on(events.MessageEdited(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID)) # Strictly scoped general edit handler
async def handle_edits_general(event):
    global low_lvl_pokemon_normal_mode

    # Check if a more specific MessageEdited handler with a pattern already handled this.
    # This is a simple check; more complex scenarios might need flags.
    if any(re.search(pattern, event.raw_text, re.IGNORECASE) for pattern in [
        r"The Safari Game has finished and you were kicked out",
        r"You have run out of Safari Balls!",
        r"You have reached the /hunt limit for the Safari Zone!",
        r"Wild .*?Safari Balls: \d+" # If it's specifically the throw prompt
    ]):
        # If the text matches a more specific handler's pattern, assume that handler took/will take care of it.
        logger.debug(f"General edit: Text matches a specific handler pattern, deferring. Text: {event.raw_text[:50]}")
        return


    # Normal Mode: Battle state updates
    if not safari_active_this_cycle and current_bot_phase == BotPhase.IN_NORMAL_HUNT:
        if "Wild" in event.raw_text and "HP" in event.raw_text and "Lv." in event.raw_text:
            if "Battle begins!" not in event.raw_text: # Avoid double processing "Battle begins!"
                logger.info("Normal Mode: Battle state updated (General Edit). Analyzing...")
                await process_battle_state_normal_mode(event)
            else:
                logger.debug("General edit: 'Battle begins!' detected, likely handled by NewMessage handler.")

    # Common: Battle conclusion / next hunt trigger (e.g., "fled", "You caught", "fainted")
    # This should only trigger if not a "game over" scenario already handled.
    elif any(substring in event.raw_text for substring in [" fled", "You caught", " fainted", "💵"]):
        if current_bot_phase == BotPhase.COMPLETED_CYCLE: # Already done with the daily cycle
            return

        logger.info(f"General edit conclusion: {event.raw_text.splitlines()[0]}. Triggering next /hunt.")
        if not safari_active_this_cycle and low_lvl_pokemon_normal_mode:
            low_lvl_pokemon_normal_mode = False
        delay = SAFARI_HUNT_COMMAND_INTERVAL if (safari_active_this_cycle and is_currently_in_safari_zone) else NORMAL_TURN_DELAY()
        await asyncio.sleep(delay)
        await send_hunt_command()

    # Normal Mode: Pokemon switching prompt
    elif not safari_active_this_cycle and current_bot_phase == BotPhase.IN_NORMAL_HUNT and "Choose your next pokemon." in event.raw_text:
        logger.info("Normal Mode: Pokemon fainted, choosing next (General Edit)...")
        await choose_next_pokemon_normal_mode(event)

    # else:
    #     logger.debug(f"General edit: No specific action taken for text: {event.raw_text[:100]}")


async def process_battle_state_normal_mode(event):
    if safari_active_this_cycle or current_bot_phase != BotPhase.IN_NORMAL_HUNT: return
    global low_lvl_pokemon_normal_mode
    wild_pokemon_name_match = re.search(r"Wild (.*?) \[.*?\]\nLv\.", event.raw_text)
    if not wild_pokemon_name_match: return
    pok_name = wild_pokemon_name_match.group(1).strip()
    wild_pokemon_hp_match = re.search(r"HP\s*(\d+)\s*/\s*(\d+)", event.raw_text)
    if not wild_pokemon_hp_match: return
    wild_current_hp, wild_max_hp = int(wild_pokemon_hp_match.group(1)), int(wild_pokemon_hp_match.group(2))
    wild_health_percentage = calculate_health_percentage(wild_max_hp, wild_current_hp)
    logger.info(f"Normal Mode Battle: {pok_name} HP {wild_current_hp}/{wild_max_hp} ({wild_health_percentage}%)")
    await asyncio.sleep(NORMAL_TURN_DELAY())
    try:
        if pok_name in regular_ball_poks:
            await click_button_sequence_normal_mode(event, ["Poke Balls", "Regular"])
        elif pok_name in repeat_ball_poks:
            is_initially_low = low_lvl_pokemon_normal_mode
            if not is_initially_low and wild_max_hp <= INITIAL_LOW_LEVEL_HP and wild_current_hp == wild_max_hp:
                 low_lvl_pokemon_normal_mode = True; is_initially_low = True
            if is_initially_low or wild_health_percentage <= HEALTH_THRESHOLD_PERCENT:
                await click_button_sequence_normal_mode(event, ["Poke Balls", "Repeat"])
            else: await event.click(0, 0); logger.info("Normal Mode: Attacked.")
        else: await event.click(0, 0); logger.info("Normal Mode: Attacked (unlisted).")
    except FloodWaitError as fwe: logger.warning(f"Flood wait ({fwe.seconds}s) in battle. Waiting."); await asyncio.sleep(fwe.seconds + 2)
    except Exception as e: logger.exception(f"Error in normal battle processing: {e}")

async def click_button_sequence_normal_mode(event, button_texts):
    current_event = event
    for i, text in enumerate(button_texts):
        try:
            click_result = await current_event.click(text=text)
            logger.info(f"Normal Mode Clicked: '{text}'")
            if click_result and hasattr(click_result, 'click'): current_event = click_result
            if i < len(button_texts) - 1: await asyncio.sleep(NORMAL_ACTION_DELAY())
        except Exception as e: logger.error(f"Normal Mode: Error clicking '{text}': {e}"); break

@client.on(events.NewMessage(chats=POKEZONE_BOT_ID, from_users=POKEZONE_BOT_ID, pattern=re.compile(r"An expert trainer", re.IGNORECASE)))
async def skipTrainer_normal_mode(event):
    if safari_active_this_cycle or current_bot_phase != BotPhase.IN_NORMAL_HUNT: return
    logger.info("Normal Mode: Expert trainer. Skipping.")
    await asyncio.sleep(NORMAL_TURN_DELAY()); await send_hunt_command()

async def choose_next_pokemon_normal_mode(event): # Event comes from a scoped handler
    preferred_pokemon_order = ["Sceptile", "Snorlax", "Sliggoo", "Scizor", "Solgaleo", "Zacian"]
    buttons = event.buttons; available_pokemon_buttons = []
    if buttons:
        for row in buttons:
            for button_obj in row: # Renamed to button_obj to avoid conflict with text
                if hasattr(button_obj, 'text'): available_pokemon_buttons.append(button_obj.text)
    logger.info(f"Normal Mode: Available Pokemon to switch: {available_pokemon_buttons}")
    clicked = False
    for preferred_pok in preferred_pokemon_order:
        if preferred_pok in available_pokemon_buttons:
            try: await event.click(text=preferred_pok); logger.info(f"Switched to {preferred_pok}."); clicked = True; break
            except Exception as e: logger.warning(f"Failed to switch to {preferred_pok}: {e}")
    if not clicked and available_pokemon_buttons:
        try: await event.click(text=available_pokemon_buttons[0]); logger.info(f"Switched to {available_pokemon_buttons[0]} (fallback).")
        except Exception as e: logger.error(f"Failed fallback switch: {e}")
    elif not clicked: logger.error("Failed to switch Pokemon.")

# --- Utility Functions ---
async def send_hunt_command():
    global bot_entity
    if not client.is_connected(): logger.warning("Tried to /hunt, but client not connected."); return
    if current_bot_phase == BotPhase.COMPLETED_CYCLE: logger.info("Cycle completed, not sending /hunt."); return
    try:
        if not bot_entity: bot_entity = await client.get_input_entity(POKEZONE_BOT_ID)
        await client.send_message(bot_entity, "/hunt")
        mode = "Safari" if (safari_active_this_cycle and is_currently_in_safari_zone) else "Normal"
        logger.info(f"Sent /hunt command (Mode: {mode}).")
    except Exception as e: logger.error(f"Error sending /hunt: {e}")

async def send_hunt_periodically_during_cycle():
    logger.info("Periodic hunt task started for this cycle.")
    while client.is_connected() and current_bot_phase not in [BotPhase.IDLE, BotPhase.COMPLETED_CYCLE]:
        interval = 90 # Default check interval
        if safari_active_this_cycle and is_currently_in_safari_zone: interval = 90 # Safari failsafe
        elif not safari_active_this_cycle and current_bot_phase == BotPhase.IN_NORMAL_HUNT: interval = 5 * 60 # Normal mode periodic
        else: interval = 30 # Shorter check during transitions/entry
        
        await asyncio.sleep(interval)

        if client.is_connected() and current_bot_phase not in [BotPhase.IDLE, BotPhase.COMPLETED_CYCLE]:
            if (safari_active_this_cycle and is_currently_in_safari_zone) or \
               (not safari_active_this_cycle and current_bot_phase == BotPhase.IN_NORMAL_HUNT):
                logger.info(f"Periodic /hunt (Interval: {interval}s).")
                await send_hunt_command()
            else: logger.debug(f"Periodic check: Not in active hunting phase ({current_bot_phase.name}), skipping /hunt.")
    logger.info("Periodic hunt task for this cycle ended.")

async def enter_safari_zone_sequence():
    global bot_entity, is_currently_in_safari_zone, current_bot_phase
    if not bot_entity: logger.error("Bot entity not resolved for Safari."); return False
    logger.info("Attempting to enter Safari Zone...")
    current_bot_phase = BotPhase.ATTEMPTING_SAFARI_ENTRY
    is_currently_in_safari_zone = False
    try:
        await client.send_message(bot_entity, "/safari"); await asyncio.sleep(random.uniform(2.0, 3.5)) # Slightly longer wait
        await client.send_message(bot_entity, "/enter")
        for _ in range(20): # Wait up to ~20 seconds for confirmation event
            if is_currently_in_safari_zone: return True
            await asyncio.sleep(1)
        logger.error("Failed to confirm Safari Zone entry via event. Assuming failure."); return False
    except Exception as e: logger.error(f"Error during Safari Zone entry sequence: {e}"); return False

# --- Main Bot Cycle and Scheduling ---
async def run_daily_bot_operations():
    global bot_entity, current_bot_phase, safari_active_this_cycle
    global is_currently_in_safari_zone, safari_balls_remaining, low_lvl_pokemon_normal_mode
    global periodic_hunt_task

    logger.info(f"--- Starting Daily Bot Operations at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
    current_bot_phase = BotPhase.IDLE # Initial state for the cycle
    safari_active_this_cycle = True # Assume starting with Safari
    is_currently_in_safari_zone = False
    safari_balls_remaining = 0
    low_lvl_pokemon_normal_mode = False
    periodic_hunt_task = None

    try:
        if not client.is_connected(): await client.connect()
        if not await client.is_user_authorized():
            logger.error("User not authorized. Cycle cannot start."); return
        logger.info("Client connected for the daily cycle.")
        if not bot_entity: bot_entity = await client.get_input_entity(POKEZONE_BOT_ID)

        periodic_hunt_task = asyncio.create_task(send_hunt_periodically_during_cycle())
        
        logger.info("Phase 1: Attempting Safari.")
        safari_entry_success = await enter_safari_zone_sequence()
        
        if safari_entry_success:
            logger.info("Safari entry successful. Safari hunting will proceed via event handlers.")
            # current_bot_phase is set to IN_SAFARI by safari_entry_confirmation
        else:
            logger.warning("Safari entry failed. Transitioning directly to Normal Hunting.")
            # Manually set phase before transition if entry fails immediately
            current_bot_phase = BotPhase.TRANSITIONING_TO_NORMAL 
            await transition_to_normal_hunting_mode("Safari entry failed")
            # transition_to_normal_hunting_mode sets current_bot_phase to IN_NORMAL_HUNT
        
        logger.info("Bot cycle active. Event handlers will manage phases and subsequent hunts...")
        await client.run_until_disconnected() # Main blocking call for the cycle
        
        logger.info("Client disconnected by handler, daily operations likely complete or interrupted.")

    except ConnectionRefusedError: logger.error("Connection refused. Telegram might be down or blocking. Cycle aborted.")
    except Exception as e: logger.exception(f"Major error during daily bot operations: {e}")
    finally:
        if periodic_hunt_task and not periodic_hunt_task.done():
            periodic_hunt_task.cancel()
            try: await periodic_hunt_task
            except asyncio.CancelledError: logger.info("Periodic hunt task explicitly cancelled.")
            except Exception as e_task: logger.error(f"Error awaiting cancelled periodic hunt task: {e_task}")
        
        if client.is_connected():
            logger.info("Ensuring client is disconnected at the very end of daily operations.")
            await client.disconnect()
        
        current_bot_phase = BotPhase.COMPLETED_CYCLE # Mark as done for this scheduled run
        logger.info(f"--- Daily Bot Operations Ended at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")

def job_wrapper():
    logger.info(f"Scheduler triggered job at {time.strftime('%Y-%m-%d %H:%M:%S')}.")
    try:
        asyncio.run(run_daily_bot_operations())
    except Exception as e:
        logger.exception("Exception running the scheduled asyncio job_wrapper:")

if __name__ == "__main__":
    logger.info(f"Bot script started. Will run daily at {SCHEDULE_TIME}.")
    logger.info(f"Target Bot ID: {POKEZONE_BOT_ID}. Notification Chat ID: {YOUR_NOTIFICATION_CHAT_ID}")

    schedule.every().day.at(SCHEDULE_TIME).do(job_wrapper)

    # For testing - run every few minutes, or once immediately:
    # schedule.every(1).minutes.do(job_wrapper) # Run every minute for quick testing
    # logger.info("TEST MODE: Running job once now for testing.")
    # job_wrapper() # Run once immediately for testing

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped manually by KeyboardInterrupt.")
    except Exception as e:
        logger.exception(f"Critical error in scheduler loop: {e}")
    finally:
        logger.info("Script shutting down.")
        # Final cleanup if needed, though run_daily_bot_operations should handle client disconnect.

# --- END OF FILE HeXakills_v3_ScheduledSafari_FullyScoped.py ---
