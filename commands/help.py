def dispatch(cmd, args, state):
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

Feed
  fyp global                             Switch to global feed
  fyp followed                           Switch to followed feed
  next                                   Load next posts
  hold                                   Pause feed paging
  resume                                 Resume feed paging

Posts
  post "content"                         Create a post
  comment <post_id> "comment"            Comment on a post
  share <post_id>                        Share a post
  quote <post_id> "text"                 Quote a post
  delete <post_id>                       Reserved for future tombstones

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
  room <name> [--private] [--ephemeral]  Create a room
  join <name>                            Join a room
  invite <username>                      Invite a user
  late [--all | <number>]                Read room messages
  leave                                  Leave current room

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
  node run [--host <host>] [--port <p>]  Run local node

Help
  help                                   Show this help
"""
    )
