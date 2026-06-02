# Rooms

Rooms are reconstructed from signed immutable objects. A room starts with a
`room` object, then changes over time through `room_event` objects.

## Room Types

Public rooms:

- visible to everyone in the room list
- joinable without an invite
- allow joined members to send room messages

Private rooms:

- visible only to the owner, members, and invited users in the UI
- require an invite before non-owners can join
- allow members to invite other users

## Creating and Joining

Create a room:

```text
beep room <name>
beep room <name> --private
beep room <name> --ephemeral 1h
```

Join a room:

```text
beep join <name>
```

The Textual UI also joins a user automatically when they open a room they are
allowed to access, including when they have a valid private-room invite.

## Invites

Invite a user:

```text
beep invite <username>
```

In the room UI command input:

```text
invite <user>
```

Invites create signed room events. An invited user still needs a join event
before they become a room member and can send messages. The UI handles that join
when the invited user opens the room.

## Messages

Send a room message from room mode:

```text
beep say "message"
```

In the room UI, use the message input at the bottom of the main room transcript.

Room messages are encrypted for current room recipients.

## Moderation

Owner-only commands:

```text
mod <user>
unmod <user>
dissolve
```

Owner and moderator commands:

```text
mute <user>
mute <user> --perma
unmute <user>
kick <user>
```

The room UI exposes one command input for room administration. It shows role
appropriate helper text:

Owner:

```text
Commands: invite <user> | mod <user> | unmod <user> | mute <user> --perma | unmute <user> | kick <user> | dissolve
```

Moderator:

```text
Commands: invite <user> | mute <user> --perma | unmute <user> | kick <user>
```

Invite-only private-room member:

```text
Command: invite <user>
```

## Ephemeral Rooms

Ephemeral rooms expire after their TTL. Supported duration examples:

```text
15s
1m
1h
2d
```

When an ephemeral room expires, `build_room_state` treats it as unavailable.

## Visibility

The UI intentionally hides private rooms from users who are not the owner, a
member, or invited. This is a UI privacy rule. Nodes may still store private room
objects they have received through sync.
