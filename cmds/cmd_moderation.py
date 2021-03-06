# Moderation commands
# bredo, 2020

import importlib

import discord, datetime, time, asyncio

import lib_db_obfuscator
importlib.reload(lib_db_obfuscator)
import lib_loaders
importlib.reload(lib_loaders)

from lib_loaders import generate_infractionid
from lib_db_obfuscator import db_hlapi


async def catch_dm_error(user, contents):
    try:
        await user.send(embed=contents)
    except (AttributeError, discord.errors.HTTPException):
        pass


async def log_infraction(message, client, user, moderator_id, infraction_reason, infraction_type):

    if not user:
        return (None, None)

    send_message = True
    with db_hlapi(message.guild.id) as database:

        # Collision test
        generated_id = generate_infractionid()
        while database.grab_infraction(generated_id):
            generated_id = generate_infractionid()

        # Grab log channel id from db
        channel_id = database.grab_config("infraction-log")

        # Generate log channel object
        if channel_id:  # If ID exists then use it
            log_channel = client.get_channel(int(channel_id))
        else:
            log_channel = None
            send_message = False

        # If channel doesnt exist simply skip it
        if not log_channel:
            send_message = False

        # Send infraction to database
        database.add_infraction(generated_id, user.id, moderator_id, infraction_type, infraction_reason, round(time.time()))

    embed = discord.Embed(title="Sonnet", description=f"New infraction for {user.mention}:", color=0x758cff)
    embed.set_thumbnail(url=user.avatar_url)
    embed.add_field(name="Infraction ID", value=str(generated_id))
    embed.add_field(name="Moderator", value=f"{client.get_user(int(moderator_id))}")
    embed.add_field(name="User", value=f"{user}")
    embed.add_field(name="Type", value=infraction_type)
    embed.add_field(name="Reason", value=infraction_reason)

    dm_embed = discord.Embed(title="Sonnet", description=f"Your punishment in {message.guild.name} has been updated:", color=0x758cff)
    dm_embed.set_thumbnail(url=user.avatar_url)
    dm_embed.add_field(name="Infraction ID", value=str(generated_id))
    dm_embed.add_field(name="Type", value=infraction_type)
    dm_embed.add_field(name="Reason", value=infraction_reason)
    if send_message:
        asyncio.create_task(log_channel.send(embed=embed))
    dm_sent = asyncio.create_task(catch_dm_error(user, dm_embed))
    return (generated_id, dm_sent)


async def process_infraction(message, args, client, infraction_type, pretty_infraction_type):

    # Check if automod
    automod = False
    try:
        if (type(args[0]) == int):
            args[0] = str(args[0])
            automod = True
    except IndexError:
        pass

    if len(args) > 1:
        reason = " ".join(args[1:])
    else:
        reason = "No Reason Specified"

    # Parse moderatorID
    if automod:
        moderator_id = client.user.id
    else:
        moderator_id = message.author.id

    # Test if user is valid
    try:
        user = message.channel.guild.get_member(int(args[0].strip("<@!>")))
        is_member = True
    except ValueError:
        await message.channel.send("Invalid User")
        raise RuntimeError("Invalid User")
    except IndexError:
        await message.channel.send("No user specified")
        raise RuntimeError("No user specified")

    if not user:
        is_member = False
        user = client.get_user(int(args[0].strip("<@!>")))
        if not user:
            user = None

    # Test if user is self
    if user and moderator_id == user.id:
        await message.channel.send(f"{pretty_infraction_type} yourself is not allowed")
        raise RuntimeError(f"Attempted self {infraction_type}")

    # Log infraction
    infraction_id, dm_sent = await log_infraction(message, client, user, moderator_id, reason, infraction_type)

    return (automod, user, reason, infraction_id, is_member, dm_sent)


async def warn_user(message, args, client, **kwargs):

    try:
        automod, user, reason, infractionID, is_member, dm_sent = await process_infraction(message, args, client, "warn", "Warning")
    except RuntimeError:
        return

    if not (automod) and user:
        await message.channel.send(f"Warned user with ID {user.id} for {reason}")
    elif not user:
        await message.channel.send("User does not exist")


async def kick_user(message, args, client, **kwargs):

    try:
        automod, user, reason, infractionID, is_member, dm_sent = await process_infraction(message, args, client, "kick", "Kicking")
    except RuntimeError:
        return

    # Attempt to kick user
    if is_member and user:
        try:
            await dm_sent  # Wait for dm to be sent before kicking
            await message.guild.kick((user), reason=reason)
        except discord.errors.Forbidden:
            await message.channel.send("The bot does not have permission to kick this user.")
            return
    else:
        await message.channel.send("User is not in this guild")
        return

    if not automod:
        await message.channel.send(f"Kicked user with ID {user.id} for {reason}")


async def ban_user(message, args, client, **kwargs):

    try:
        automod, user, reason, infractionID, is_member, dm_sent = await process_infraction(message, args, client, "ban", "Banning")
    except RuntimeError:
        return

    # Attempt to ban user
    try:
        if is_member:
            await dm_sent  # Wait for dm to be sent before banning
        await message.channel.guild._state.http.ban(args[0].strip("<@!>"), message.channel.guild.id, 0, reason=reason)

    except discord.errors.Forbidden:
        await message.channel.send("The bot does not have permission to ban this user.")
        return
    except (discord.errors.NotFound, discord.errors.HTTPException):
        await message.channel.send("This user does not exist")
        return

    if not automod:
        await message.channel.send(f"Banned user with ID {args[0].strip('<@!>')} for {reason}")


async def unban_user(message, args, client, **kwargs):

    # Test if user is valid
    try:
        user = await client.fetch_user(int(args[0].strip("<@!>")))
    except ValueError:
        await message.channel.send("Invalid User")
        return
    except IndexError:
        await message.channel.send("No user specified")
        return

    if not user:
        await message.channel.send("Invalid User")
        return

    # Attempt to unban user
    try:
        await message.guild.unban(user)
    except discord.errors.Forbidden:
        await message.channel.send("The bot does not have permission to unban this user.")
        return
    except discord.errors.NotFound:
        await message.channel.send("This user is not banned")
        return

    await message.channel.send(f"Unbanned user with ID {user.id}")


async def mute_user(message, args, client, **kwargs):

    if len(args) >= 2:
        try:
            multiplicative_factor = {"s": 1, "m": 60, "h": 3600}
            tmptime = args[1]
            if not tmptime[-1] in ["s", "m", "h"]:
                mutetime = int(tmptime)
                del args[1]
            else:
                mutetime = int(tmptime[:-1]) * multiplicative_factor[tmptime[-1]]
                del args[1]
        except (ValueError, TypeError):
            mutetime = 0
    else:
        mutetime = 0

    try:
        automod, user, reason, infractionID, is_member, dm_sent = await process_infraction(message, args, client, "mute", "Muting")
    except RuntimeError:
        return

    if not user:
        await message.channel.send("User does not exist")
        return

    # Check they are in the guild
    if not is_member:
        await message.channel.send("User is not in this guild")
        return

    # Get muterole from DB
    with db_hlapi(message.guild.id) as db:
        mute_role = db.grab_config("mute-role")

    if mute_role:
        mute_role = message.guild.get_role(int(mute_role))
        if not mute_role:
            await message.channel.send("ERROR: no muterole set")
            return
    else:
        await message.channel.send("ERROR: no muterole set")
        return

    # Attempt to mute user
    try:
        await user.add_roles(mute_role)
    except discord.errors.Forbidden:
        await message.channel.send("The bot does not have permission to mute this user.")
        return

    if not automod and not mutetime:
        await message.channel.send(f"Muted user with ID {user.id} for {reason}")

    if mutetime:
        if not automod:
            asyncio.create_task(message.channel.send(f"Muted user with ID {user.id} for {mutetime}s for {reason}"))
        # add to mutedb
        with db_hlapi(message.guild.id) as db:
            db.mute_user(user.id, time.time() + mutetime, infractionID)

        await asyncio.sleep(mutetime)

        # unmute in db
        with db_hlapi(message.guild.id) as db:
            if db.is_muted(infractionid=infractionID):
                db.unmute_user(infractionid=infractionID)

                try:
                    await user.remove_roles(mute_role)
                except discord.errors.Forbidden:
                    pass


async def unmute_user(message, args, client, **kwargs):

    # Test if user is valid
    try:
        user = message.channel.guild.get_member(int(args[0].strip("<@!>")))
    except ValueError:
        await message.channel.send("Invalid User")
        return
    except IndexError:
        await message.channel.send("No user specified")
        return

    if not user:
        await message.channel.send("Invalid User")
        return

    # Get muterole from DB
    with db_hlapi(message.guild.id) as db:
        mute_role = db.grab_config("mute-role")
        db.unmute_user(userid=user.id)

    if mute_role:
        mute_role = message.guild.get_role(int(mute_role))
        if not mute_role:
            await message.channel.send("ERROR: no muterole set")
            return
    else:
        await message.channel.send("ERROR: no muterole set")
        return

    # Attempt to unmute user
    try:
        await user.remove_roles(mute_role)
    except discord.errors.Forbidden:
        await message.channel.send("The bot does not have permission to unmute this user.")
        return

    await message.channel.send(f"Unmuted user with ID {user.id}")


async def search_infractions(message, args, client, **kwargs):

    try:
        user = client.get_user(int(args[0].strip("<@!>")))
    except ValueError:
        await message.channel.send("Invalid User")
        return
    except IndexError:
        await message.channel.send("No user specified")
        return

    if not user:
        user_id = int(args[0].strip("<@!>"))
    else:
        user_id = user.id

    with db_hlapi(message.guild.id) as db:
        infractions = db.grab_user_infractions(user_id)

    # Sort newest first
    infractions.sort(reverse=True, key=lambda a: a[5])

    # Generate chunks from infractions
    do_not_exceed = 1900  # Discord message length limits
    chunks = [""]
    curchunk = 0
    for i in infractions:
        infraction_data = ", ".join([i[0], i[3], i[4]]) + "\n"
        if (len(chunks[curchunk]) + len(infraction_data)) > do_not_exceed:
            curchunk += 1
            chunks.append("")
        else:
            chunks[curchunk] = chunks[curchunk] + infraction_data

    # Parse pager
    if len(args) >= 2:
        try:
            selected_chunk = int(float(args[1])) - 1
        except ValueError:
            selected_chunk = 0
    else:
        selected_chunk = 0

    # Test if valid page
    try:
        outdata = chunks[selected_chunk]
    except IndexError:
        outdata = chunks[0]
        selected_chunk = 0

    if infractions:
        await message.channel.send(f"Page {selected_chunk+1} of {len(chunks)} ({len(infractions)} infractions)\n```css\nID, Type, Reason\n{outdata}```")
    else:
        await message.channel.send("No infractions found")


async def get_detailed_infraction(message, args, client, **kwargs):

    if args:
        with db_hlapi(message.guild.id) as db:
            infraction = db.grab_infraction(args[0])
        if not infraction:
            await message.channel.send("Infraction ID does not exist")
            return
    else:
        await message.channel.send("No argument supplied")
        return

    infraction_id, user_id, moderator_id, infraction_type, reason, timestamp = infraction

    infraction_embed = discord.Embed(title="Infraction Search", description=f"Infraction for <@{user_id}>:", color=0x758cff)
    infraction_embed.add_field(name="Infraction ID", value=infraction_id)
    infraction_embed.add_field(name="Moderator", value=f"<@{moderator_id}>")
    infraction_embed.add_field(name="Type", value=infraction_type)
    infraction_embed.add_field(name="Reason", value=reason)
    infraction_embed.timestamp = datetime.datetime.utcfromtimestamp(int(timestamp))

    await message.channel.send(embed=infraction_embed)


async def delete_infraction(message, args, client, **kwargs):

    if args:
        with db_hlapi(message.guild.id) as db:
            infraction = db.grab_infraction(args[0])
            db.delete_infraction(infraction[0])
        if not infraction:
            await message.channel.send("Infraction ID does not exist")
            return
    else:
        await message.channel.send("No argument supplied")
        return

    infraction_id, user_id, moderator_id, infraction_type, reason, timestamp = infraction

    infraction_embed = discord.Embed(title="Infraction Deleted", description=f"Infraction for <@{user_id}>:", color=0xd62d20)
    infraction_embed.add_field(name="Infraction ID", value=infraction_id)
    infraction_embed.add_field(name="Moderator", value=f"<@{moderator_id}>")
    infraction_embed.add_field(name="Type", value=infraction_type)
    infraction_embed.add_field(name="Reason", value=reason)
    infraction_embed.timestamp = datetime.datetime.utcfromtimestamp(int(timestamp))

    await message.channel.send(embed=infraction_embed)


category_info = {'name': 'moderation', 'pretty_name': 'Moderation', 'description': 'Moderation commands.'}

commands = {
    'warn': {
        'pretty_name': 'warn <uid>',
        'description': 'Warn a user',
        'permission': 'moderator',
        'cache': 'keep',
        'execute': warn_user
        },
    'kick': {
        'pretty_name': 'kick <uid>',
        'description': 'Kick a user',
        'permission': 'moderator',
        'cache': 'keep',
        'execute': kick_user
        },
    'ban': {
        'pretty_name': 'ban <uid>',
        'description': 'Ban a user',
        'permission': 'moderator',
        'cache': 'keep',
        'execute': ban_user
        },
    'unban': {
        'pretty_name': 'unban <uid>',
        'description': 'Unban a user',
        'permission': 'moderator',
        'cache': 'keep',
        'execute': unban_user
        },
    'mute': {
        'pretty_name': 'mute <uid> [time[h|m|S]]',
        'description': 'Mute a user, defaults to no unmute (0s)',
        'permission': 'moderator',
        'cache': 'keep',
        'execute': mute_user
        },
    'unmute': {
        'pretty_name': 'unmute <uid>',
        'description': 'Unmute a user',
        'permission': 'moderator',
        'cache': 'keep',
        'execute': unmute_user
        },
    'search-infractions': {
        'pretty_name': 'search-infractions <uid>',
        'description': 'Grab infractions of a user',
        'permission': 'moderator',
        'cache': 'keep',
        'execute': search_infractions
        },
    'infraction-details':
        {
            'pretty_name': 'infraction-details <infractionID>',
            'description': 'Grab details of an infractionID',
            'permission': 'moderator',
            'cache': 'keep',
            'execute': get_detailed_infraction
            },
    'delete-infraction':
        {
            'pretty_name': 'delete-infraction <infractionID>',
            'description': 'Delete an infraction by infractionID',
            'permission': 'administrator',
            'cache': 'keep',
            'execute': delete_infraction
            }
    }

version_info = "1.1.0"
