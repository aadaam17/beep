# commands/help.py

from core.types import CommandState

def dispatch(cmd: str, args: str, state: CommandState) -> None:
    print(
        """
Beep - Anonymous CLI Social Network
==================================

Note:
  - Always prefix commands with `beep`
  - Example: beep post "hello world"

Identity & Session
  register -u <username> -p <password>   Create local identity
  login -u <username> -p <password>      Unlock identity
  logout                                 Lock identity
  backup create --file <path>            Create encrypted backup file
  backup create --mnemonic               Show mnemonic recovery phrase
  backup import --file <path>            Import encrypted backup file
  restore --file <path>                  Restore local identity from backup file
  restore --mnemonic "<phrase>" -p <pw>  Restore from mnemonic and set local password
  restore recover                        Recover missing IRO-indexed objects from peers

Feed
  fyp global                             Switch to global feed
  fyp followed                           Switch to followed feed
  next                                   Load next posts
  hold                                   Pause feed paging
  resume                                 Resume feed paging

Posts
  post "content"                         Create a post
  comment <object_id> "comment"          Reply to a post or comment
  share <post_id>                        Share a post
  quote <post_id> "text"                 Quote a post
  delete <post_id>                       Reserved for future tombstones
  view <object_id>                       Show a post/comment thread by ID

Profile
  profile                                View your profile
  profile <username>                     View another profile
  profile --followers                    Show followers
  profile --following                    Show following
  profile --posts                        Show authored posts
  profile --shared                       Show shared and quoted posts

Follow
  follow <username>                      Follow a user
  unfollow <username>                    Unfollow a user

Chat
  chat                                   List chats
  chat <username>                        Enter direct chat
  say "message"                          Send message in chat or room
  read [--all | <number>]                Read chat messages
  exit                                   Leave current chat

Rooms
  room                                   List rooms
  room <name> [--private] [--ephemeral <ttl>]  Create a room
  join <name>                            Join a room
  invite <username>                      Invite a user
  late [--all | <number>]                Read room messages
  leave                                  Leave current room
  dissolve                               Dissolve the current room (owner only)
  --ephemeral                            Default room expiry is 24 hours
  --ephemeral 15s|1m|1h|2d               Custom room expiry

Moderation
  mute <username>                        Mute a user
  unmute <username>                      Unmute a user
  kick <username>                        Remove a user from a room
  mod <username>                         Make a member a moderator
  unmod <username>                       Remove moderator status

Node
  peer add <url>                         Add a peer
  peer remove <url>                      Remove a peer
  peer list                              Show configured peers
  sync                                   Synchronize objects with peers
  node run [--port <p>]                  Run local node
  storage status [--reason <reason>]     Show retention summary
  storage inspect <object_id>            Show why an object is retained
  storage prune [--apply]                Dry-run or apply pruning

Help
  help                                   Show this help
"""
    )
