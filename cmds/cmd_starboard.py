# Starboard system
# Ultrabear 2020

import os

from lib_parsers import parse_boolean, update_log_channel
from lib_mdb_handler import db_handler, db_error
from sonnet_cfg import STARBOARD_EMOJI

async def starboard_channel_change(message, args, client, stats, cmds):
    try:
        await update_log_channel(message, args, client, "archive-channel")
    except RuntimeError:
        return


async def set_starboard_emoji(message, args, client, stats, cmds):

    if not message.author.permissions_in(message.channel).administrator:
        await message.channel.send("Insufficient permissions.")
        return

    if args:
        emoji = args[0]
    else:
        emoji = STARBOARD_EMOJI

    try:
        with db_handler() as database:
            database.add_to_table(f"{message.guild.id}_config",[["property", "starboard-emoji"],["value", emoji]])
    except db_error.OperationalError:
        await message.channel.send("Database error, run recreate-db")
        return

    os.remove(f"datastore/{message.guild.id}.cache.db")
    await message.channel.send(f"Updated starboard emoji to {emoji}")


async def set_starboard_use(message, args, client, stats, cmds):

    if not message.author.permissions_in(message.channel).administrator:
        await message.channel.send("Insufficient permissions.")
        return

    if args:
        gate = parse_boolean(args[0])
    else:
        gate = False

    try:
        with db_handler() as database:
            database.add_to_table(f"{message.guild.id}_config",[["property", "starboard-enabled"],["value", int(gate)]])
    except db_error.OperationalError:
        await message.channel.send("Database error, run recreate-db")
        return

    os.remove(f"datastore/{message.guild.id}.cache.db")
    await message.channel.send(f"Starboard set to {bool(gate)}")


async def set_starboard_count(message, args, client, stats, cmds):

    if not message.author.permissions_in(message.channel).administrator:
        await message.channel.send("Insufficient permissions.")
        return

    if args:
        try:
            count = int(float(args[0]))
        except ValueError:
            await message.channel.send("Invalid input, please enter a number")
            return
    else:
        await message.channel.send("No input")
        return

    try:
        with db_handler() as database:
            database.add_to_table(f"{message.guild.id}_config",[["property","starboard-count"],["value",count]])
    except db_error.OperationalError:
        await message.channel.send("Database error, run recreate-db")

    os.remove(f"datastore/{message.guild.id}.cache.db")
    await message.channel.send(f"Updated starboard count to {count}")


category_info = {
    'name': 'starboard',
    'pretty_name': 'Starboard',
    'description': 'Starboard commands.'
}


commands = {
    'starboard-channel': {
        'pretty_name': 'starboard-channel',
        'description': 'Change Starboard for this guild.',
        'execute': starboard_channel_change
    },
    'starboard-emoji': {
        'pretty_name': 'starboard-emoji',
        'description': 'Set the starboard emoji',
        'execute': set_starboard_emoji
    },
    'starboard-enabled': {
        'pretty_name': 'starboard-enabled',
        'description': 'Toggle starboard on or off',
        'execute': set_starboard_use
    },
    'starboard-count': {
        'pretty_name': 'starboard-count',
        'description': 'Set starboard reaction count',
        'execute': set_starboard_count
    }        
}
