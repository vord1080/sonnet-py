# Moderation commands
# bredo, 2020

import discord, datetime, time, random, asyncio

from lib_mdb_handler import db_handler, db_hlapi
from lib_loaders import generate_infractionid


async def log_infraction(message, client, user_id, moderator_id, infraction_reason, infraction_type):
    send_message = True
    with db_handler() as database:

        # Collision test
        generated_id = generate_infractionid()
        while database.fetch_rows_from_table(f"{message.guild.id}_infractions", ["infractionID", generated_id]):
            generated_id = generate_infractionid()

        # Grab log channel id from db
        channel_id = database.fetch_rows_from_table(f"{message.guild.id}_config", ["property", "infraction-log"])



        # Generate log channel object
        if channel_id:  # If ID exists then use it
            log_channel = client.get_channel(int(channel_id[0][1]))
        else:
            log_channel = None
            send_message = False

        # If channel doesnt exist simply skip it
        if not log_channel:
            send_message = False


        # Send infraction to database
        database.add_to_table(f"{message.guild.id}_infractions", [
            ["infractionID", generated_id],
            ["userID", user_id],
            ["moderatorID", moderator_id],
            ["type", infraction_type],
            ["reason", infraction_reason],
            ["timestamp", round(time.time())]
            ])

    user = client.get_user(int(user_id))

    embed = discord.Embed(title="Sonnet", description=f"New infraction for <@{user_id}>:", color=0x758cff)
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
        await log_channel.send(embed=embed)
    try: # If the user is a bot it cannot be DM'd
        await user.send(embed=dm_embed)
    except AttributeError:
        pass

async def process_infraction(message, args, client, infraction_type):

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
        user = client.get_user(int(args[0].strip("<@!>")))
    except ValueError:
        await message.channel.send("Invalid User")
        raise RuntimeError("Invalid User")
    except IndexError:
        await message.channel.send("No user specified")
        raise RuntimeError("No user specified")

    if not user:
        await message.channel.send("Invalid User")
        raise RuntimeError("Invalid User")

    # Test if user is self
    if moderator_id == user.id:
        await message.channel.send(f"{infraction_type[0].upper()+infraction_type[1:]}ing yourself is not allowed")
        raise RuntimeError(f"Attempted self {infraction_type}")


    # Log infraction
    await log_infraction(message, client, user.id, moderator_id, reason, infraction_type)

    return (automod, user, reason)


async def warn_user(message, args, client, stats, cmds):

    try:
        automod, user, reason = await process_infraction(message, args, client, "warn")
    except RuntimeError:
        return

    if not automod:
        await message.channel.send(f"Warned user with ID {user.id} for {reason}")


async def kick_user(message, args, client, stats, cmds):

    try:
        automod, user, reason = await process_infraction(message, args, client, "kick")
    except RuntimeError:
        return

    # Attempt to kick user
    try:
        await message.guild.kick((user), reason=reason)
    except discord.errors.Forbidden:
        await message.channel.send("The bot does not have permission to kick this user.")
        return

    if not automod:
        await message.channel.send(f"Kicked user with ID {user.id} for {reason}")


async def ban_user(message, args, client, stats, cmds):

    try:
        automod, user, reason = await process_infraction(message, args, client, "ban")
    except RuntimeError:
        return

    # Attempt to ban user
    try:
        await message.guild.ban(user, reason=reason, delete_message_days=0)
    except discord.errors.Forbidden:
        await message.channel.send("The bot does not have permission to ban this user.")
        return

    if not automod:
        await message.channel.send(f"Banned user with ID {user.id} for {reason}")


async def mute_user(message, args, client, stats, cmds):

    try:
        automod, user, reason = await process_infraction(message, args, client, "mute")
    except RuntimeError:
        return

    # Get muterole from DB
    with db_handler() as database:
        mute_role = database.fetch_rows_from_table(f"{message.guild.id}_config", ["property","mute-role"])

    if mute_role:
        mute_role = message.guild.get_role(mute_role[0][1])
        if not mute_role:
            await message.channel.send("ERROR: no muterole set")
            return
    else:
        await message.channel.send("ERROR: no muterole set")
        return

    # Attempt to mute user
    try:
        await message.author.add_roles(mute_role)
    except discord.errors.Forbidden:
        await message.channel.send("The bot does not have permission to mute this user.")
        return

    if not automod:
        await message.channel.send(f"Muted user with ID {user.id} for {reason}")

    # add auto unmute, mute database, default mute length, mute length


async def search_infractions(message, args, client, stats, cmds):

    try:
        user = client.get_user(int(args[0].strip("<@!>")))
    except ValueError:
        await message.channel.send("Invalid User")
        return
    except IndexError:
        await message.channel.send("No user specified")
        return

    if not user:
        await message.channel.send("Invalid User")
        return

    with db_hlapi(message.guild.id) as db:
        infractions = db.grab_user_infractions(user.id)

    # Generate chunks from infractions
    do_not_exceed = 1950  # Discord message length limits
    chunks = [""]
    curchunk = 0
    for i in infractions:
        infraction_data = ", ".join([i[0],i[3],i[4]]) + "\n"
        if (len(chunks[curchunk]) + len(infraction_data)) > do_not_exceed:
            curchunk += 1
            chunks.append("")
        else:
            chunks[curchunk] = chunks[curchunk] + infraction_data

    # Parse pager
    if len(args) >= 2:
        try:
            selected_chunk = int(float(args[1]))-1
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

    await message.channel.send(f"Page {selected_chunk+1} of {len(chunks)}\n```css\nID, Type, Reason\n{outdata}```")


async def get_detailed_infraction(message, args, client, stats, cmds):

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


async def delete_infraction(message, args, client, stats, cmds):

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


category_info = {
    'name': 'moderation',
    'pretty_name': 'Moderation',
    'description': 'Moderation commands.'
}


commands = {
    'warn': {
        'pretty_name': 'warn',
        'description': 'Warn a user',
        'permission':'moderator',
        'execute': warn_user
    },
    'kick': {
        'pretty_name': 'kick',
        'description': 'Kick a user',
        'permission':'moderator',
        'execute': kick_user
    },
    'ban': {
        'pretty_name': 'ban',
        'description': 'Ban a user',
        'permission':'moderator',
        'execute': ban_user
    },
    'mute': {
        'pretty_name': 'mute',
        'description': 'Mute a user',
        'permission':'moderator',
        'execute': mute_user
    },
    'search-infractions': {
        'pretty_name': 'search-infractions',
        'description': 'Grab infractions of a user',
        'permission':'moderator',
        'execute': search_infractions
    },
    'infraction-details': {
        'pretty_name': 'infraction-details',
        'description': 'Grab details of an infractionID',
        'permission':'moderator',
        'execute': get_detailed_infraction
    },
    'delete-infraction': {
        'pretty_name': 'delete-infraction',
        'description': 'Delete an infraction by infractionID',
        'permission':'administrator',
        'execute': delete_infraction
    }
    
}
