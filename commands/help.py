# commands/help.py
"""Help command to display usage instructions."""

from core.types import CommandState

def dispatch(cmd: str, args: str, state: CommandState) -> None:
    print(
        """
Beep - Anonymous CLI Social Network
==================================

Note:
  - Default mode: beep
  - Command mode: open `python cli.py`, then type `beep post "hello world"`
  - Live mode: open `python cli.py`, then type `beep fyp --live`
  - Interactive mode: python cli.py shell
  - Bare `beep` opens the original persistent text command shell
  - beep shell launches the Textual app UI when available

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
  fyp --live                             Refresh the feed continuously
  next                                   Load next posts
  hold                                   Pause feed paging
  resume                                 Resume feed paging

Posts
  post "content"                         Create a post
  comment <object_id> "comment"          Reply to a post or comment
  share <post_id>                        Share a post
  quote <post_id> "text"                 Quote a post
  delete <post_id>                       Publish a signed tombstone for your post
  view <object_id>                       Show a post/comment thread by ID

Profile
  profile                                View your profile
  profile <username|username#handle>     View another profile
  profile --followers                    Show followers
  profile --following                    Show following
  profile --posts                        Show authored posts
  profile --shared                       Show shared and quoted posts
  profile --rotate-key                   Rotate encryption key and revoke old key ID

Follow
  follow <username|username#handle>      Follow a user
  unfollow <username|username#handle>    Unfollow a user

Chat
  chat                                   List chats
  chat <username|username#handle>        Enter direct chat
  chat <username|username#handle> --live Tail a direct chat live
  say "message"                          Send message in chat or room
  read [--all | <number>]                Read chat messages
  exit                                   Leave current chat

Rooms
  room                                   List rooms
  room <name> [--private] [--ephemeral <ttl>]  Create a room
  join <name>                            Join a room
  join <name> --live                     Join a room and tail new messages live
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
  connect                                Show your Beep handle
  connect <username|username#handle>     Resolve a known identity
  network                                Show unified network status
  network setup                          Show bootstrap guidance
  network setup --relay <url>            Add a relay through the guided network flow
  network setup --peer <url>             Add a direct peer through the guided network flow
  network check                          Check reachability of configured peers and relays
  network check --live                   Continuously rerun network checks
  peer add <url>                         Add a peer
  peer remove <url>                      Remove a peer
  peer list                              Show configured peers
  relay add <url>                        Add a relay node
  relay remove <url>                     Remove a relay node
  relay list                             Show configured relays
  relay policy                           Show network and relay policy
  relay policy set ...                   Update relay strategy, quotas, auth, or public endpoint
  sync                                   Synchronize objects with peers
  node status                            Show node-mode policy and runtime status
  node enable                            Enable hosting on this device
  node disable                           Disable hosting and stop tracked background node
  node run [--port <p>]                  Run public/manual local node
  login/register                         Prompt capable devices before enabling node mode
  storage status [--reason <reason>]     Show retention summary
  storage inspect <object_id>            Show why an object is retained
  storage prune [--apply]                Dry-run or apply pruning

Help
  beep                                   Open persistent text command mode
  shell                                  Open the Textual interactive app shell
  help                                   Show this help
"""
    )
