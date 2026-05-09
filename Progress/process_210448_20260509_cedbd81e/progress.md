# oneExportPerFile run

Started: 2026-05-09T21:04:48.402779+00:00

- repo:        /home/user/git/stemwise
- target dir:  /home/user/git/stemwise/src/hooks
- max-files:   3
- merge-file-branches: True
- Progress log: /home/user/git/jedi/Progress/process_210448_20260509_cedbd81e/progress.md
- Original branch: main
- Main branch:     JediBranch/oneExportPerFile/210448-20260509

## File: use-mobile.tsx

- Exports found (1): ['useIsMobile']
- Only 1 export — skipping.

## File: use-toast.ts

- Exports found (1): ['reducer']
- Only 1 export — skipping.

## File: useAcclimatingData.ts

- Exports found (6): ['AcclimatingBatch', 'useAcclimatingBatches', 'useAcclimatingMap', 'useCreateAcclimatingBatch', 'useUpdateAcclimatingBatch', 'useDeleteAcclimatingBatch']
- ERROR processing useAcclimatingData.ts: Command failed (exit 128): git checkout -b JediBranch/oneExportPerFile/210448-20260509/useAcclimatingData
stdout: 
stderr: fatal: cannot lock ref 'refs/heads/JediBranch/oneExportPerFile/210448-20260509/useAcclimatingData': 'refs/heads/JediBranch/oneExportPerFile/210448-20260509' exists; cannot create 'refs/heads/JediBranch/oneExportPerFile/210448-20260509/useAcclimatingData'

- Returned to original branch: main

## Summary

- total_files: 3
- skipped: 2
- split: 0
- merged: 0
- errors: 1
