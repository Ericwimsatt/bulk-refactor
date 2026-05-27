# collectPageSpecificFiles run

Started: 2026-05-27T00:26:54.267048+00:00

- repo:                     /Users/ericwimsatt/git/jedi-targets/manhunt/manhunt-app
- roots_dir:                /Users/ericwimsatt/git/jedi-targets/manhunt/manhunt-app/app
- target_dir:               /Users/ericwimsatt/git/jedi-targets/manhunt/manhunt-app/components
- file_based_routing_pages: True
- Warning: Working tree is not clean. Commit or stash changes before running this workflow. Proceeding anyway because this workflow uses an isolated worktree.
- Original branch: main
- git_root:                 /Users/ericwimsatt/git/jedi-targets/manhunt
- Main branch:   JediBranch/collectPageSpecificFiles/002654-20260527/base
- Main worktree: /Users/ericwimsatt/git/jedi-targets/manhunt/.jedi-worktrees/manhunt-app/JediBranch--collectPageSpecificFiles--002654-20260527--base
- Root files (5): ['game.tsx', 'index.tsx', 'rules.tsx', '_layout.tsx', 'player.tsx']
- Target files: 10
- Total TS files scanned: 32

## Building importer map

-   components/NavBar.tsx: imported by ['_layout.tsx', 'index.tsx', 'AppShell.tsx']
-   components/TeamBadge.tsx: imported by ['PlayerList.tsx']
-   components/PlayerList.tsx: imported by []
-   components/AppShell.tsx: imported by ['game.tsx', 'rules.tsx', 'player.tsx']
-   components/InfoCard.tsx: imported by ['rules.tsx', 'player.tsx']
-   components/LobbyJoinCard.tsx: imported by []
-   components/AppProviders.tsx: imported by ['_layout.tsx']
-   components/styles/lobbyStyles.ts: imported by ['TeamBadge.tsx', 'PlayerList.tsx', 'LobbyJoinCard.tsx']
-   components/styles/tokens.ts: imported by ['index.tsx', 'ClaimAdminCard.tsx', 'AdminControls.tsx', 'SectionCard.tsx', 'PlayerRow.tsx', 'TeamSection.tsx', 'AdminPlayerRow.tsx', 'NavBar.tsx', 'TeamBadge.tsx', 'lobbyStyles.ts', 'layoutStyles.ts', 'map.tsx']
-   components/styles/layoutStyles.ts: imported by ['PlayerList.tsx', 'AppShell.tsx', 'InfoCard.tsx', 'LobbyJoinCard.tsx']
-   Claimed components/AppProviders.tsx → _layout.tsx

## Moving 1 file(s)

- Skipping special root file _layout.tsx — not moving
- No moves performed (all root files were special/skipped).
