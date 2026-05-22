# SplitLargeComponent run

Started: 2026-05-21T00:28:37.432057+00:00

- repo:              /Users/ericwimsatt/git/jedi-targets/manhunt/manhunt-app
- target:            app/lobby.tsx
- components-dir:    components
- max-files:         None
- merge-file-branches: False
- Progress log: /Users/ericwimsatt/git/jedi/src/Progress/process_002837_20260521_3454b8df/progress.md
- Original branch: split-try
- Git root:        /Users/ericwimsatt/git/jedi-targets/manhunt
- Main branch:     JediBranch/SplitLargeComponent/002837-20260521/base
- Main worktree:   /Users/ericwimsatt/git/jedi-targets/manhunt/.jedi-worktrees/manhunt-app/JediBranch--SplitLargeComponent--002837-20260521--base

## Phase 1: Scanning files for split candidates


## File: lobby.tsx

-   Candidate reason: contains 5 conditional JSX branches
-   Created file branch: JediBranch/SplitLargeComponent/002837-20260521/lobby (worktree: /Users/ericwimsatt/git/jedi-targets/manhunt/.jedi-worktrees/manhunt-app/JediBranch--SplitLargeComponent--002837-20260521--lobby)

## Phase 2: Parallel OpenCode (1 tasks, 1 workers)


## OpenCode: lobby.tsx

-   Invoking opencode: You are refactoring the file `app/lobby.tsx` in a TypeScript/React Native project.

The automated scanner flagged this file for component splitting because:
  - contains 5 conditional JSX branches

Your task — Component Extraction:
1. Identify JSX sub-trees that should become their own components:
   a. Any conditional branch where BOTH arms render meaningful JSX (e.g. admin panel vs
      guest notice). Create a separate component for each arm OR a unified component that
      accepts a prop to toggle the variant.
   b. Any `.map()` call that returns JSX longer than ~3 lines. Extract the item renderer
      into its own component (e.g. `PlayerRow`, `TeamCard`).
2. Create each new component as its OWN file inside `components/`.
   - Name the file after the component (PascalCase, e.g. `AdminControls.tsx`).
   - Each new file must export EXACTLY ONE component.
3. Pass props to make the extracted components reusable:
   - Prefer generic, prop-driven designs over one-off specialised components.
   - Do NOT hard-code data that can be passed as a prop.
4. IMPORTANT — do NOT split for mobile/desktop differences:
   - Keep identical data-fetching hooks in the same component regardless of device.
   - Only extract a platform-specific component when it must be ENTIRELY ABSENT on the
     other platform (e.g. a map overlay that only exists on native).
5. Update `app/lobby.tsx` to import and render the new components.
6. Update any other imports across the project that reference moved symbols.
7. Do NOT commit any changes — leave them as uncommitted edits.
8. After making all changes run the linter: `bun run lint`
9. Output a brief summary listing every new file created and every existing file modified.

Keep the original component's overall logic and data-fetching unchanged. You are only
extracting pieces of the JSX render tree into dedicated component files.

-   opencode error: [Errno 2] No such file or directory: 'opencode'
-   No uncommitted changes after opencode (may have self-committed or no changes).
- Done with lobby.tsx.

## Phase 4: Cleanup

- Removed main worktree: /Users/ericwimsatt/git/jedi-targets/manhunt/.jedi-worktrees/manhunt-app/JediBranch--SplitLargeComponent--002837-20260521--base

## Summary

- total_files: 1
- skipped: 0
- split: 1
- merged: 0
- errors: 0
- opencode_used: 1
