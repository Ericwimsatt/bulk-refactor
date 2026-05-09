# oneExportPerFile run

Started: 2026-05-09T21:07:25.487810+00:00

- repo:        /home/user/git/stemwise
- target dir:  /home/user/git/stemwise/src/hooks
- max-files:   5
- merge-file-branches: True
- Progress log: /home/user/git/jedi/Progress/process_210725_20260509_3ca646b2/progress.md
- Original branch: main
- Main branch:     JediBranch/oneExportPerFile/210725-20260509/base

## File: use-mobile.tsx

- Exports found (1): ['useIsMobile']
- Only 1 export — skipping.

## File: use-toast.ts

- Exports found (3): ['reducer', 'useToast', 'toast']
- Created file branch: JediBranch/oneExportPerFile/210725-20260509/use-toast
-   Removed 'export' from 'reducer' — committed d3a258e9a9c6e26012e956f8dd6f15ea85f4f6ce.

```diff
diff --git a/src/hooks/use-toast.ts b/src/hooks/use-toast.ts
index ca1316d..ca319ed 100644
--- a/src/hooks/use-toast.ts
+++ b/src/hooks/use-toast.ts
@@ -68,7 +68,7 @@ const addToRemoveQueue = (toastId: string) => {
   toastTimeouts.set(toastId, timeout);
 };
 
-export const reducer = (state: State, action: Action): State => {
+const reducer = (state: State, action: Action): State => {
   switch (action.type) {
     case "ADD_TOAST":
       return {
```

-   'useToast' is imported elsewhere — keeping export.
-   'toast' is imported elsewhere — keeping export.
- After pass 1: 2 export(s) remain — ['useToast', 'toast']
-   Invoking opencode to split use-toast.ts (exports: useToast, toast)

### opencode/use-toast.ts

```
Let me check the re-export file and understand all importers:
Now I have a complete picture. Let me create the three new files, update all importers, and clean up.
Good, no naming conflict. Let me create all files in parallel:
Now let me delete the original file and update all importers:
Now let me run the linter to verify:
Linter passes with no new errors — all 322 issues are pre-existing in the codebase (none related to my changes).

Here's the summary:

**Created files (3):**
- `src/hooks/toast-store.ts` — shared state machine (reducer, dispatch, listeners, genId) — single default export
- `src/hooks/toast.ts` — the `toast` function — single named export `{ toast }`
- `src/hooks/useToast.ts` — the `useToast` hook — single named export `{ useToast }`

**Deleted file (1):**
- `src/hooks/use-toast.ts` — original file with 2 exports, replaced by the 3 files above

**Modified files (5):**
- `src/pages/Signup.tsx` — import updated → `@/hooks/useToast`
- `src/pages/Login.tsx` — import updated → `@/hooks/useToast`
- `src/hooks/useOnboarding.ts` — import updated → `@/hooks/useToast`
- `src/components/ui/toaster.tsx` — import updated → `@/hooks/useToast`
- `src/components/ui/use-toast.ts` — reduced to single re-export of `useToast` only
```

-   opencode step completed.
-   Committed opencode changes — 974b91eee7390d9326d5a18f1830290ca541fce8

```diff
diff --git a/src/components/ui/toaster.tsx b/src/components/ui/toaster.tsx
index 2cba1c8..f0d241d 100644
--- a/src/components/ui/toaster.tsx
+++ b/src/components/ui/toaster.tsx
@@ -1,4 +1,4 @@
-import { useToast } from "@/hooks/use-toast";
+import { useToast } from "@/hooks/useToast";
 import { Toast, ToastClose, ToastDescription, ToastProvider, ToastTitle, ToastViewport } from "@/components/ui/toast";
 
 export function Toaster() {
diff --git a/src/components/ui/use-toast.ts b/src/components/ui/use-toast.ts
index b0aef21..82a2341 100644
--- a/src/components/ui/use-toast.ts
+++ b/src/components/ui/use-toast.ts
@@ -1,3 +1,3 @@
-import { useToast, toast } from "@/hooks/use-toast";
+import { useToast } from "@/hooks/useToast";
 
-export { useToast, toast };
+export { useToast };
diff --git a/src/hooks/use-toast.ts b/src/hooks/use-toast.ts
deleted file mode 100644
index ca319ed..0000000
--- a/src/hooks/use-toast.ts
+++ /dev/null
@@ -1,186 +0,0 @@
-import * as React from "react";
-
-import type { ToastActionElement, ToastProps } from "@/components/ui/toast";
-
-const TOAST_LIMIT = 1;
-const TOAST_REMOVE_DELAY = 1000000;
-
-type ToasterToast = ToastProps & {
-  id: string;
-  title?: React.ReactNode;
-  description?: React.ReactNode;
-  action?: ToastActionElement;
-};
-
-const actionTypes = {
-  ADD_TOAST: "ADD_TOAST",
-  UPDATE_TOAST: "UPDATE_TOAST",
-  DISMISS_TOAST: "DISMISS_TOAST",
-  REMOVE_TOAST: "REMOVE_TOAST",
-} as const;
-
-let count = 0;
-
-function genId() {
-  count = (count + 1) % Number.MAX_SAFE_INTEGER;
-  return count.toString();
-}
-
-type ActionType = typeof actionTypes;
-
-type Action =
-  | {
-      type: ActionType["ADD_TOAST"];
-      toast: ToasterToast;
-    }
-  | {
-      type: ActionType["UPDATE_TOAST"];
-      toast: Partial<ToasterToast>;
-    }
-  | {
-      type: ActionType["DISMISS_TOAST"];
-      toastId?: ToasterToast["id"];
-    }
-  | {
-      type: ActionType["REMOVE_TOAST"];
-      toastId?: ToasterToast["id"];
-    };
-
-interface State {
-  toasts: ToasterToast[];
-}
-
-const toastTimeouts = new Map<string, ReturnType<typeof setTimeout>>();
-
-const addToRemoveQueue = (toastId: string) => {
-  if (toastTimeouts.has(toastId)) {
-    return;
-  }
-
-  const timeout = setTimeout(() => {
-    toastTimeouts.delete(toastId);
-    dispatch({
-      type: "REMOVE_TOAST",
-      toastId: toastId,
-    });
-  }, TOAST_REMOVE_DELAY);
-
-  toastTimeouts.set(toastId, timeout);
-};
-
-const reducer = (state: State, action: Action): State => {
-  switch (action.type) {
-    case "ADD_TOAST":
-      return {
-        ...state,
-        toasts: [action.toast, ...state.toasts].slice(0, TOAST_LIMIT),
-      };
-
-    case "UPDATE_TOAST":
-      return {
-        ...state,
-        toasts: state.toasts.map((t) => (t.id === action.toast.id ? { ...t, ...action.toast } : t)),
-      };
-
-    case "DISMISS_TOAST": {
-      const { toastId } = action;
-
-      // ! Side effects ! - This could be extracted into a dismissToast() action,
-      // but I'll keep it here for simplicity
-      if (toastId) {
-        addToRemoveQueue(toastId);
-      } else {
-        state.toasts.forEach((toast) => {
-          addToRemoveQueue(toast.id);
-        });
-      }
-
-      return {
-        ...state,
-        toasts: state.toasts.map((t) =>
-          t.id === toastId || toastId === undefined
-            ? {
-                ...t,
-                open: false,
-              }
-            : t,
-        ),
-      };
-    }
-    case "REMOVE_TOAST":
-      if (action.toastId === undefined) {
-        return {
-          ...state,
-          toasts: [],
-        };
-      }
-      return {
-        ...state,
-        toasts: state.toasts.filter((t) => t.id !== action.toastId),
-      };
-  }
-};
-
-const listeners: Array<(state: State) => void> = [];
-
-let memoryState: State = { toasts: [] };
-
-function dispatch(action: Action) {
-  memoryState = reducer(memoryState, action);
-  listeners.forEach((listener) => {
-    listener(memoryState);
-  });
-}
-
-type Toast = Omit<ToasterToast, "id">;
-
-function toast({ ...props }: Toast) {
-  const id = genId();
-
-  const update = (props: ToasterToast) =>
-    dispatch({
-      type: "UPDATE_TOAST",
-      toast: { ...props, id },
-    });
-  const dismiss = () => dispatch({ type: "DISMISS_TOAST", toastId: id });
-
-  dispatch({
-    type: "ADD_TOAST",
-    toast: {
-      ...props,
-      id,
-      open: true,
-      onOpenChange: (open) => {
-        if (!open) dismiss();
-      },
-    },
-  });
-
-  return {
-    id: id,
-    dismiss,
-    update,
-  };
-}
-
-function useToast() {
-  const [state, setState] = React.useState<State>(memoryState);
-
-  React.useEffect(() => {
-    listeners.push(setState);
-    return () => {
-      const index = listeners.indexOf(setState);
-      if (index > -1) {
-        listeners.splice(index, 1);
-      }
-    };
-  }, [state]);
-
-  return {
-    ...state,
-    toast,
-    dismiss: (toastId?: string) => dispatch({ type: "DISMISS_TOAST", toastId }),
-  };
-}
-
-export { useToast, toast };
diff --git a/src/hooks/useOnboarding.ts b/src/hooks/useOnboarding.ts
index c817d58..327d76e 100644
--- a/src/hooks/useOnboarding.ts
+++ b/src/hooks/useOnboarding.ts
@@ -1,7 +1,7 @@
 import { useState, useEffect, useCallback } from "react";
 import { supabase } from "@/integrations/supabase/client";
 import { useAuth } from "@/contexts/AuthContext";
-import { useToast } from "@/hooks/use-toast";
+import { useToast } from "@/hooks/useToast";
 
 export interface OnboardingState {
   step: number;
diff --git a/src/pages/Login.tsx b/src/pages/Login.tsx
index 1eaf488..b4b1c48 100644
--- a/src/pages/Login.tsx
+++ b/src/pages/Login.tsx
@@ -6,7 +6,7 @@ import { Input } from "@/components/ui/input";
 import { Label } from "@/components/ui/label";
 import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
 import { supabase } from "@/integrations/supabase/client";
-import { useToast } from "@/hooks/use-toast";
+import { useToast } from "@/hooks/useToast";
 import { useAuth } from "@/contexts/AuthContext";
 import { Navigate } from "react-router-dom";
 
diff --git a/src/pages/Signup.tsx b/src/pages/Signup.tsx
index ce491c1..01c2ff8 100644
--- a/src/pages/Signup.tsx
+++ b/src/pages/Signup.tsx
@@ -6,7 +6,7 @@ import { Input } from "@/components/ui/input";
 import { Label } from "@/components/ui/label";
 import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
 import { supabase } from "@/integrations/supabase/client";
-import { useToast } from "@/hooks/use-toast";
+import { useToast } from "@/hooks/useToast";
 import { useAuth } from "@/contexts/AuthContext";
 import { Navigate } from "react-router-dom";
```

- Merged JediBranch/oneExportPerFile/210725-20260509/use-toast → JediBranch/oneExportPerFile/210725-20260509/base (sha: 0ea6a4aad752a0123a46a9e62f719f7e59fbc5ec)
- Done with use-toast.ts.

## File: useAcclimatingData.ts

- Exports found (6): ['AcclimatingBatch', 'useAcclimatingBatches', 'useAcclimatingMap', 'useCreateAcclimatingBatch', 'useUpdateAcclimatingBatch', 'useDeleteAcclimatingBatch']
- Created file branch: JediBranch/oneExportPerFile/210725-20260509/useAcclimatingData
-   'AcclimatingBatch' is imported elsewhere — keeping export.
-   'useAcclimatingBatches' is imported elsewhere — keeping export.
-   'useAcclimatingMap' is imported elsewhere — keeping export.
-   'useCreateAcclimatingBatch' is imported elsewhere — keeping export.
-   'useUpdateAcclimatingBatch' is imported elsewhere — keeping export.
-   'useDeleteAcclimatingBatch' is imported elsewhere — keeping export.
- After pass 1: 6 export(s) remain — ['AcclimatingBatch', 'useAcclimatingBatches', 'useAcclimatingMap', 'useCreateAcclimatingBatch', 'useUpdateAcclimatingBatch', 'useDeleteAcclimatingBatch']
-   Invoking opencode to split useAcclimatingData.ts (exports: AcclimatingBatch, useAcclimatingBatches, useAcclimatingMap, useCreateAcclimatingBatch, useUpdateAcclimatingBatch, useDeleteAcclimatingBatch)

### opencode/useAcclimatingData.ts

```
Now let me read all the files that import from `useAcclimatingData`:
Let me create all 7 new files in parallel:
Now let me update imports in all 6 consumer files:
Now let me delete the original file and run the linter:
Linter passes — all errors are pre-existing `@typescript-eslint/no-explicit-any` issues, none related to our refactoring.
Summary of changes:

**Created (7 new files):**
- `src/hooks/AcclimatingBatch.ts` — the `AcclimatingBatch` interface
- `src/hooks/TABLE.ts` — the `TABLE` constant (shared helper)
- `src/hooks/useAcclimatingBatches.ts` — the `useAcclimatingBatches` hook
- `src/hooks/useAcclimatingMap.ts` — the `useAcclimatingMap` hook
- `src/hooks/useCreateAcclimatingBatch.ts` — the `useCreateAcclimatingBatch` mutation
- `src/hooks/useUpdateAcclimatingBatch.ts` — the `useUpdateAcclimatingBatch` mutation
- `src/hooks/useDeleteAcclimatingBatch.ts` — the `useDeleteAcclimatingBatch` mutation

**Deleted:**
- `src/hooks/useAcclimatingData.ts` — original file removed entirely

**Modified imports (6 files):**
- `src/components/purchasing/ReceiveOrderWizard.tsx`
- `src/components/inventory/MarkAcclimatingModal.tsx`
- `src/components/inventory/ConvertModal.tsx`
- `src/components/inventory/AcclimatingBatchesModal.tsx`
- `src/components/orders/NewOrderDrawer.tsx`
- `src/pages/Inventory.tsx`
```

-   opencode step completed.
-   Committed opencode changes — a45a648cc3826a7b532b5653ca9f12be6746a10a

```diff
diff --git a/src/components/inventory/AcclimatingBatchesModal.tsx b/src/components/inventory/AcclimatingBatchesModal.tsx
index 1388e13..0b767da 100644
--- a/src/components/inventory/AcclimatingBatchesModal.tsx
+++ b/src/components/inventory/AcclimatingBatchesModal.tsx
@@ -9,7 +9,9 @@ import { Textarea } from "@/components/ui/textarea";
 import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
 import { ScrollArea } from "@/components/ui/scroll-area";
 import { Pencil, Trash2 } from "lucide-react";
-import { AcclimatingBatch, useDeleteAcclimatingBatch, useUpdateAcclimatingBatch } from "@/hooks/useAcclimatingData";
+import { AcclimatingBatch } from "@/hooks/AcclimatingBatch";
+import { useDeleteAcclimatingBatch } from "@/hooks/useDeleteAcclimatingBatch";
+import { useUpdateAcclimatingBatch } from "@/hooks/useUpdateAcclimatingBatch";
 
 type Filter = "all" | "expiring" | "expired";
 
diff --git a/src/components/inventory/ConvertModal.tsx b/src/components/inventory/ConvertModal.tsx
index 5287278..fa0e63f 100644
--- a/src/components/inventory/ConvertModal.tsx
+++ b/src/components/inventory/ConvertModal.tsx
@@ -14,7 +14,7 @@ import {
 } from "@/components/ui/dialog";
 import { PlantViewModel, useConvertStage } from "@/hooks/useInventoryData";
 import { useConversionProfiles } from "@/hooks/useConversionProfiles";
-import { useCreateAcclimatingBatch } from "@/hooks/useAcclimatingData";
+import { useCreateAcclimatingBatch } from "@/hooks/useCreateAcclimatingBatch";
 import { useUserProfile } from "@/hooks/useSettingsData";
 import { STAGE_LABELS } from "@/lib/businessConstants";
 import { Sprout } from "lucide-react";
diff --git a/src/components/inventory/MarkAcclimatingModal.tsx b/src/components/inventory/MarkAcclimatingModal.tsx
index 292e29a..e0d9de3 100644
--- a/src/components/inventory/MarkAcclimatingModal.tsx
+++ b/src/components/inventory/MarkAcclimatingModal.tsx
@@ -10,7 +10,7 @@ import { Calendar } from "@/components/ui/calendar";
 import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
 import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
 import { cn } from "@/lib/utils";
-import { useCreateAcclimatingBatch } from "@/hooks/useAcclimatingData";
+import { useCreateAcclimatingBatch } from "@/hooks/useCreateAcclimatingBatch";
 import { useUserProfile } from "@/hooks/useSettingsData";
 import { PlantViewModel, StageCounts } from "@/hooks/useInventoryData";
 
diff --git a/src/components/orders/NewOrderDrawer.tsx b/src/components/orders/NewOrderDrawer.tsx
index 843e80f..23bfda1 100644
--- a/src/components/orders/NewOrderDrawer.tsx
+++ b/src/components/orders/NewOrderDrawer.tsx
@@ -11,7 +11,7 @@ import { Switch } from "@/components/ui/switch";
 import { Badge } from "@/components/ui/badge";
 import { Plus, Trash2, ChevronDown, Check, AlertTriangle } from "lucide-react";
 import { useOrdersData } from "@/hooks/useOrdersData";
-import { useAcclimatingMap } from "@/hooks/useAcclimatingData";
+import { useAcclimatingMap } from "@/hooks/useAcclimatingMap";
 import { useInventoryLotsAvg } from "@/hooks/useInventoryLotsAvg";
 import { ShippingProfileModal } from "./ShippingProfileModal";
 import { getMarginColorClass, mapPaymentMethodLabelToValue } from "@/lib/businessConstants";
diff --git a/src/components/purchasing/ReceiveOrderWizard.tsx b/src/components/purchasing/ReceiveOrderWizard.tsx
index 150544b..0496283 100644
--- a/src/components/purchasing/ReceiveOrderWizard.tsx
+++ b/src/components/purchasing/ReceiveOrderWizard.tsx
@@ -14,7 +14,7 @@ import { Progress } from "@/components/ui/progress";
 import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
 import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
 import { PurchaseOrderViewModel, ReceiveLineData, useReceiveOrder, useActiveVarieties } from "@/hooks/usePurchasingData";
-import { useCreateAcclimatingBatch } from "@/hooks/useAcclimatingData";
+import { useCreateAcclimatingBatch } from "@/hooks/useCreateAcclimatingBatch";
 import { useUserProfile } from "@/hooks/useSettingsData";
 import { backfillMissingSkus } from "@/lib/skuUtils";
 import { useAuth } from "@/contexts/AuthContext";
diff --git a/src/hooks/useAcclimatingData.ts b/src/hooks/useAcclimatingData.ts
deleted file mode 100644
index 22d649d..0000000
--- a/src/hooks/useAcclimatingData.ts
+++ /dev/null
@@ -1,173 +0,0 @@
-import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
-import { supabase } from "@/integrations/supabase/client";
-import { useAuth } from "@/contexts/AuthContext";
-import { toast } from "sonner";
-
-export interface AcclimatingBatch {
-  id: string;
-  variety_id: string;
-  stage: string;
-  tier: string | null;
-  quantity: number;
-  started_at: string;
-  expires_at: string;
-  notes: string | null;
-  created_at: string | null;
-  variety_name?: string;
-}
-
-const TABLE = "acclimating_batches";
-
-export function useAcclimatingBatches() {
-  const { user } = useAuth();
-  const qc = useQueryClient();
-
-  return useQuery({
-    queryKey: [TABLE, user?.id],
-    enabled: !!user,
-    queryFn: async () => {
-      // Auto-clear expired batches client-side based on user settings
-      const { data: profile } = await supabase
-        .from("user_profiles")
-        .select("auto_clear_acclimating")
-        .eq("user_id", user!.id)
-        .maybeSingle();
-
-      if (profile?.auto_clear_acclimating) {
-        // Try calling the DB function, fallback to client-side delete
-        try {
-          await (supabase as any).rpc("clear_expired_acclimating_batches");
-        } catch {
-          // Fallback: delete expired batches directly
-          await (supabase as any)
-            .from(TABLE)
-            .delete()
-            .eq("user_id", user!.id)
-            .lt("expires_at", new Date().toISOString());
-        }
-      }
-
-      const { data, error } = await (supabase as any)
-        .from(TABLE)
-        .select("id, variety_id, stage, tier, quantity, started_at, expires_at, notes, created_at, plant_varieties(name)")
-        .eq("user_id", user!.id)
-        .order("expires_at", { ascending: true });
-      if (error) throw error;
-
-      return ((data ?? []) as any[]).map((d) => ({
-        id: d.id,
-        variety_id: d.variety_id,
-        stage: d.stage,
-        tier: d.tier,
-        quantity: d.quantity,
-        started_at: d.started_at,
-        expires_at: d.expires_at,
-        notes: d.notes,
-        created_at: d.created_at,
-        variety_name: d.plant_varieties?.name ?? "Unknown",
-      })) as AcclimatingBatch[];
-    },
-  });
-}
-
-/** Map: variety_id -> stage -> total acclimating qty */
-export function useAcclimatingMap() {
-  const { data: batches } = useAcclimatingBatches();
-  const map = new Map<string, Record<string, { total: number; hasExpired: boolean }>>();
-  for (const b of batches ?? []) {
-    if (!map.has(b.variety_id)) map.set(b.variety_id, {});
-    const stageMap = map.get(b.variety_id)!;
-    if (!stageMap[b.stage]) stageMap[b.stage] = { total: 0, hasExpired: false };
-    stageMap[b.stage].total += b.quantity;
-    if (new Date(b.expires_at) < new Date()) stageMap[b.stage].hasExpired = true;
-  }
-  return map;
-}
-
-export function useCreateAcclimatingBatch() {
-  const { user } = useAuth();
-  const qc = useQueryClient();
-
-  return useMutation({
-    mutationFn: async (input: {
-      variety_id: string;
-      stage: string;
-      tier?: string | null;
-      quantity: number;
-      started_at: string;
-      expires_at: string;
-      notes?: string;
-    }) => {
-      if (!user) throw new Error("Not authenticated");
-      const { error } = await (supabase as any)
-        .from(TABLE)
-        .insert({
-          user_id: user.id,
-          variety_id: input.variety_id,
-          stage: input.stage,
-          tier: input.tier || null,
-          quantity: input.quantity,
-          started_at: input.started_at,
-          expires_at: input.expires_at,
-          notes: input.notes || null,
-        });
-      if (error) throw error;
-    },
-    onSuccess: () => {
-      qc.invalidateQueries({ queryKey: [TABLE] });
-      toast.success("Acclimating batch created");
-    },
-    onError: (e: Error) => toast.error(e.message),
-  });
-}
-
-export function useUpdateAcclimatingBatch() {
-  const { user } = useAuth();
-  const qc = useQueryClient();
-
-  return useMutation({
-    mutationFn: async (input: {
-      id: string;
-      quantity?: number;
-      started_at?: string;
-      expires_at?: string;
-      notes?: string | null;
-    }) => {
-      if (!user) throw new Error("Not authenticated");
-      const { id, ...vals } = input;
-      const { error } = await (supabase as any)
-        .from(TABLE)
-        .update(vals)
-        .eq("id", id)
-        .eq("user_id", user.id);
-      if (error) throw error;
-    },
-    onSuccess: () => {
-      qc.invalidateQueries({ queryKey: [TABLE] });
-      toast.success("Batch updated");
-    },
-    onError: (e: Error) => toast.error(e.message),
-  });
-}
-
-export function useDeleteAcclimatingBatch() {
-  const { user } = useAuth();
-  const qc = useQueryClient();
-
-  return useMutation({
-    mutationFn: async (id: string) => {
-      if (!user) throw new Error("Not authenticated");
-      const { error } = await (supabase as any)
-        .from(TABLE)
-        .delete()
-        .eq("id", id)
-        .eq("user_id", user.id);
-      if (error) throw error;
-    },
-    onSuccess: () => {
-      qc.invalidateQueries({ queryKey: [TABLE] });
-      toast.success("Batch cleared");
-    },
-    onError: (e: Error) => toast.error(e.message),
-  });
-}
diff --git a/src/pages/Inventory.tsx b/src/pages/Inventory.tsx
index 283b150..9842e2c 100644
--- a/src/pages/Inventory.tsx
+++ b/src/pages/Inventory.tsx
@@ -6,7 +6,8 @@ import { Badge } from "@/components/ui/badge";
 import { Skeleton } from "@/components/ui/skeleton";
 import { useInventoryViewModels, useCategories, PlantViewModel } from "@/hooks/useInventoryData";
 import { useOwedToOrders } from "@/hooks/useOwedToOrders";
-import { useAcclimatingBatches, useAcclimatingMap } from "@/hooks/useAcclimatingData";
+import { useAcclimatingBatches } from "@/hooks/useAcclimatingBatches";
+import { useAcclimatingMap } from "@/hooks/useAcclimatingMap";
 import { useUserProfile } from "@/hooks/useSettingsData";
 import { StageSummaryCards } from "@/components/inventory/StageSummaryCards";
 import { FilterBar } from "@/components/inventory/FilterBar";
```

- Merged JediBranch/oneExportPerFile/210725-20260509/useAcclimatingData → JediBranch/oneExportPerFile/210725-20260509/base (sha: 98df3434e5d879132a63b667d465451f0442b1dd)
- Done with useAcclimatingData.ts.

## File: useActiveLots.ts

- Exports found (2): ['ActiveLot', 'useActiveLots']
- Created file branch: JediBranch/oneExportPerFile/210725-20260509/useActiveLots
-   'ActiveLot' is imported elsewhere — keeping export.
-   'useActiveLots' is imported elsewhere — keeping export.
- After pass 1: 2 export(s) remain — ['ActiveLot', 'useActiveLots']
-   Invoking opencode to split useActiveLots.ts (exports: ActiveLot, useActiveLots)

### opencode/useActiveLots.ts

```
Lint passes (only pre-existing errors remain). Here's the summary:

**Created:**
- `src/hooks/ActiveLot.ts` — single export: `ActiveLot` interface

**Modified:**
- `src/hooks/useActiveLots.ts` — removed `ActiveLot` export; now imports it from `./ActiveLot`; only exports `useActiveLots`
- `src/components/lots/LotPicker.tsx` — split the combined import into two separate lines (`import { useActiveLots } from "@/hooks/useActiveLots"` + `import type { ActiveLot } from "@/hooks/ActiveLot"`)
```

-   opencode step completed.
-   Committed opencode changes — 370ff4d5333ff0a74ce76074675916eca7a6d40d

```diff
diff --git a/src/components/lots/LotPicker.tsx b/src/components/lots/LotPicker.tsx
index 2240646..f843d5b 100644
--- a/src/components/lots/LotPicker.tsx
+++ b/src/components/lots/LotPicker.tsx
@@ -6,7 +6,8 @@ import { Button } from "@/components/ui/button";
 import { Badge } from "@/components/ui/badge";
 import { Label } from "@/components/ui/label";
 import { Skeleton } from "@/components/ui/skeleton";
-import { useActiveLots, type ActiveLot } from "@/hooks/useActiveLots";
+import { useActiveLots } from "@/hooks/useActiveLots";
+import type { ActiveLot } from "@/hooks/ActiveLot";
 
 export interface LotSelection {
   lot_id: string;
diff --git a/src/hooks/useActiveLots.ts b/src/hooks/useActiveLots.ts
index 33d82b7..d7dfe34 100644
--- a/src/hooks/useActiveLots.ts
+++ b/src/hooks/useActiveLots.ts
@@ -1,14 +1,6 @@
 import { useQuery } from "@tanstack/react-query";
 import { supabase } from "@/integrations/supabase/client";
-
-export interface ActiveLot {
-  id: string;
-  received_at: string;
-  true_cost_per_plant: number;
-  remaining_quantity: number;
-  source_type: string;
-  created_at: string;
-}
+import type { ActiveLot } from "./ActiveLot";
 
 interface UseActiveLotsParams {
   varietyId: string;
```

- Merged JediBranch/oneExportPerFile/210725-20260509/useActiveLots → JediBranch/oneExportPerFile/210725-20260509/base (sha: 81a1595e2cdfc7a5c454e52f50c711025fe1a710)
- Done with useActiveLots.ts.

## File: useAnalyticsData.ts

- Exports found (9): ['AnalyticsPeriod', 'DateRange', 'getAnalyticsDateRange', 'GoalsData', 'useGoals', 'useAnalyticsSalesData', 'useAnalyticsInventoryData', 'useAnalyticsExpensesData', 'useAnalyticsSuppliersData']
- Created file branch: JediBranch/oneExportPerFile/210725-20260509/useAnalyticsData
-   'AnalyticsPeriod' is imported elsewhere — keeping export.
-   'DateRange' is imported elsewhere — keeping export.
-   'getAnalyticsDateRange' is imported elsewhere — keeping export.
-   'GoalsData' is imported elsewhere — keeping export.
-   'useGoals' is imported elsewhere — keeping export.
-   'useAnalyticsSalesData' is imported elsewhere — keeping export.
-   'useAnalyticsInventoryData' is imported elsewhere — keeping export.
-   'useAnalyticsExpensesData' is imported elsewhere — keeping export.
-   'useAnalyticsSuppliersData' is imported elsewhere — keeping export.
- After pass 1: 9 export(s) remain — ['AnalyticsPeriod', 'DateRange', 'getAnalyticsDateRange', 'GoalsData', 'useGoals', 'useAnalyticsSalesData', 'useAnalyticsInventoryData', 'useAnalyticsExpensesData', 'useAnalyticsSuppliersData']
-   Invoking opencode to split useAnalyticsData.ts (exports: AnalyticsPeriod, DateRange, getAnalyticsDateRange, GoalsData, useGoals, useAnalyticsSalesData, useAnalyticsInventoryData, useAnalyticsExpensesData, useAnalyticsSuppliersData)

### opencode/useAnalyticsData.ts

```
Now I'll create all the new files. Let me also check the lint command first:
Creating the first batch of simple files in parallel:
Now update the imports in the two consumer files and delete the original:
Linter passes (no new errors introduced — all 322 are pre-existing).

## Summary

**Deleted:**
- `src/hooks/useAnalyticsData.ts` — original file with 9 exports

**Created (10 files, each with exactly 1 export):**
- `src/hooks/AnalyticsPeriod.ts` — `AnalyticsPeriod` type
- `src/hooks/DateRange.ts` — `DateRange` interface
- `src/hooks/GoalsData.ts` — `GoalsData` interface
- `src/hooks/fmt.ts` — `fmt` utility (shared by `useAnalyticsSalesData` & `useAnalyticsExpensesData`)
- `src/hooks/getAnalyticsDateRange.ts` — `getAnalyticsDateRange` function
- `src/hooks/useGoals.ts` — `useGoals` hook (with internal `DEFAULT_GOALS`)
- `src/hooks/useAnalyticsSalesData.ts` — `useAnalyticsSalesData` hook
- `src/hooks/useAnalyticsInventoryData.ts` — `useAnalyticsInventoryData` hook
- `src/hooks/useAnalyticsExpensesData.ts` — `useAnalyticsExpensesData` hook
- `src/hooks/useAnalyticsSuppliersData.ts` — `useAnalyticsSuppliersData` hook

**Modified (2 files with updated imports):**
- `src/pages/Analytics.tsx` — split the single bulk import into 7 individual imports
- `src/components/analytics/GoalsSection.tsx` — split import into `useGoals` and `GoalsData` from separate files
```

-   opencode step completed.
-   Committed opencode changes — 27d32282946031d811900f81638d5883ddc7be65

```diff
diff --git a/src/components/analytics/GoalsSection.tsx b/src/components/analytics/GoalsSection.tsx
index feaa6e8..57f8efb 100644
--- a/src/components/analytics/GoalsSection.tsx
+++ b/src/components/analytics/GoalsSection.tsx
@@ -6,7 +6,8 @@ import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "
 import { Input } from "@/components/ui/input";
 import { Label } from "@/components/ui/label";
 import { Progress } from "@/components/ui/progress";
-import { useGoals, GoalsData } from "@/hooks/useAnalyticsData";
+import { useGoals } from "@/hooks/useGoals";
+import type { GoalsData } from "@/hooks/GoalsData";
 
 interface GoalCardProps {
   label: string;
diff --git a/src/hooks/useAnalyticsData.ts b/src/hooks/useAnalyticsData.ts
deleted file mode 100644
index 024265b..0000000
--- a/src/hooks/useAnalyticsData.ts
+++ /dev/null
@@ -1,457 +0,0 @@
-import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
-import { supabase } from "@/integrations/supabase/client";
-import { useAuth } from "@/contexts/AuthContext";
-import {
-  startOfWeek, endOfWeek, startOfMonth, endOfMonth, startOfQuarter, endOfQuarter,
-  startOfYear, endOfYear, subMonths, subQuarters, subYears, format,
-} from "date-fns";
-import { toast } from "sonner";
-import { STAGE_ORDER, STAGE_LABELS } from "@/lib/businessConstants";
-
-export type AnalyticsPeriod = "this_week" | "this_month" | "this_quarter" | "this_year" | "last_month" | "last_quarter" | "last_year" | "custom";
-
-export interface DateRange {
-  from: Date;
-  to: Date;
-}
-
-export function getAnalyticsDateRange(period: AnalyticsPeriod, custom?: DateRange): DateRange {
-  const now = new Date();
-  switch (period) {
-    case "this_week": return { from: startOfWeek(now), to: endOfWeek(now) };
-    case "this_month": return { from: startOfMonth(now), to: endOfMonth(now) };
-    case "this_quarter": return { from: startOfQuarter(now), to: endOfQuarter(now) };
-    case "this_year": return { from: startOfYear(now), to: endOfYear(now) };
-    case "last_month": { const d = subMonths(now, 1); return { from: startOfMonth(d), to: endOfMonth(d) }; }
-    case "last_quarter": { const d = subQuarters(now, 1); return { from: startOfQuarter(d), to: endOfQuarter(d) }; }
-    case "last_year": { const d = subYears(now, 1); return { from: startOfYear(d), to: endOfYear(d) }; }
-    case "custom": return custom ?? { from: startOfMonth(now), to: endOfMonth(now) };
-  }
-}
-
-const fmt = (d: Date) => format(d, "yyyy-MM-dd");
-
-export interface GoalsData {
-  id?: string;
-  monthly_revenue_target: number;
-  monthly_profit_target: number;
-  monthly_order_target: number;
-  monthly_expense_budget: number;
-  inventory_value_target: number;
-  survival_rate_target: number;
-}
-
-const DEFAULT_GOALS: GoalsData = {
-  monthly_revenue_target: 5000,
-  monthly_profit_target: 2000,
-  monthly_order_target: 20,
-  monthly_expense_budget: 1000,
-  inventory_value_target: 10000,
-  survival_rate_target: 95,
-};
-
-export function useGoals() {
-  const { user } = useAuth();
-  const qc = useQueryClient();
-
-  const query = useQuery({
-    queryKey: ["business_goals", user?.id],
-    enabled: !!user,
-    queryFn: async () => {
-      const { data } = await supabase.from("business_goals").select("*").eq("user_id", user!.id).maybeSingle();
-      if (data) return data as GoalsData & { id: string };
-      // Auto-create defaults
-      const { data: created } = await supabase.from("business_goals").insert({ user_id: user!.id, ...DEFAULT_GOALS }).select().single();
-      return created as GoalsData & { id: string };
-    },
-  });
-
-  const updateMutation = useMutation({
-    mutationFn: async (goals: Partial<GoalsData>) => {
-      const { error } = await supabase.from("business_goals").update(goals).eq("user_id", user!.id);
-      if (error) throw error;
-    },
-    onSuccess: () => { qc.invalidateQueries({ queryKey: ["business_goals"] }); toast.success("Goals updated"); },
-    onError: () => toast.error("Failed to update goals"),
-  });
-
-  return { goals: query.data, isLoading: query.isLoading, updateGoals: updateMutation.mutateAsync };
-}
-
-export function useAnalyticsSalesData(range: DateRange, compareRange?: DateRange) {
-  const { user } = useAuth();
-  const from = fmt(range.from);
-  const to = fmt(range.to);
-  const cFrom = compareRange ? fmt(compareRange.from) : null;
-  const cTo = compareRange ? fmt(compareRange.to) : null;
-
-  return useQuery({
-    queryKey: ["analytics_sales", user?.id, from, to, cFrom, cTo],
-    enabled: !!user,
-    queryFn: async () => {
-      const [ordersRes, itemsRes, varietiesRes, platformsRes, salesTypesRes, adjRes] = await Promise.all([
-        supabase.from("orders").select("id, subtotal, gross_profit, total_cogs, shipping_label_cost, packaging_cost_total, sale_date, status, platform_id, sales_type_id, payment_method").eq("user_id", user!.id),
-        supabase.from("order_items").select("order_id, variety_id, stage, tier, quantity, line_total, line_profit, line_cogs, price_per_plant, cogs_per_plant").eq("user_id", user!.id),
-        supabase.from("plant_varieties").select("id, name, category_id").eq("user_id", user!.id),
-        supabase.from("sales_platforms").select("id, name").eq("user_id", user!.id),
-        supabase.from("sales_types").select("id, name, platform_id").eq("user_id", user!.id),
-        supabase.from("order_adjustments").select("order_id, amount, adjustment_type").eq("user_id", user!.id),
-      ]);
-
-      const allCompleted = (ordersRes.data ?? []).filter(o => o.status === "completed");
-      const filterByRange = (orders: typeof allCompleted, f: string, t: string) =>
-        orders.filter(o => o.sale_date >= f && o.sale_date <= t);
-
-      const current = filterByRange(allCompleted, from, to);
-      const compare = cFrom && cTo ? filterByRange(allCompleted, cFrom, cTo) : [];
-
-      const items = itemsRes.data ?? [];
-      const varMap = new Map((varietiesRes.data ?? []).map(v => [v.id, v.name]));
-      const platMap = new Map((platformsRes.data ?? []).map(p => [p.id, p.name]));
-      const stMap = new Map((salesTypesRes.data ?? []).map(s => [s.id, { name: s.name, platformId: s.platform_id }]));
-      const adjustments = adjRes.data ?? [];
-
-      const calcStats = (orders: typeof allCompleted) => {
-        const orderIds = new Set(orders.map(o => o.id));
-        const revenue = orders.reduce((s, o) => s + Number(o.subtotal ?? 0), 0);
-        const grossProfit = orders.reduce((s, o) => s + Number(o.gross_profit ?? 0), 0);
-        const shipping = orders.reduce((s, o) => s + Number(o.shipping_label_cost ?? 0) + Number(o.packaging_cost_total ?? 0), 0);
-        const totalCogs = orders.reduce((s, o) => s + Number(o.total_cogs ?? 0), 0);
-        const adjTotal = adjustments.filter(a => orderIds.has(a.order_id)).reduce((s, a) => s + Number(a.amount), 0);
-        const netProfit = grossProfit - shipping - adjTotal;
-        const avgOrderValue = orders.length > 0 ? revenue / orders.length : 0;
-
-        // Best single day
-        const byDate: Record<string, number> = {};
-        orders.forEach(o => { byDate[o.sale_date] = (byDate[o.sale_date] ?? 0) + Number(o.subtotal ?? 0); });
-        const bestDay = Object.entries(byDate).sort((a, b) => b[1] - a[1])[0];
-
-        // Revenue trend
-        const trendMap: Record<string, { revenue: number; profit: number; orders: number }> = {};
-        orders.forEach(o => {
-          if (!trendMap[o.sale_date]) trendMap[o.sale_date] = { revenue: 0, profit: 0, orders: 0 };
-          trendMap[o.sale_date].revenue += Number(o.subtotal ?? 0);
-          trendMap[o.sale_date].profit += Number(o.gross_profit ?? 0) - Number(o.shipping_label_cost ?? 0) - Number(o.packaging_cost_total ?? 0);
-          trendMap[o.sale_date].orders += 1;
-        });
-        const trend = Object.entries(trendMap).sort(([a], [b]) => a.localeCompare(b)).map(([date, v]) => ({ date, ...v }));
-
-        // By platform
-        const platStats: Record<string, { name: string; revenue: number; orders: number; profit: number; cogs: number; margin: number }> = {};
-        orders.forEach(o => {
-          const name = o.platform_id ? platMap.get(o.platform_id) ?? "Unknown" : "Direct";
-          if (!platStats[name]) platStats[name] = { name, revenue: 0, orders: 0, profit: 0, cogs: 0, margin: 0 };
-          platStats[name].revenue += Number(o.subtotal ?? 0);
-          platStats[name].orders += 1;
-          platStats[name].profit += Number(o.gross_profit ?? 0) - Number(o.shipping_label_cost ?? 0) - Number(o.packaging_cost_total ?? 0);
-          platStats[name].cogs += Number(o.total_cogs ?? 0);
-        });
-        Object.values(platStats).forEach(p => { p.margin = p.revenue > 0 ? (p.profit / p.revenue) * 100 : 0; });
-        const byPlatform = Object.values(platStats).sort((a, b) => b.revenue - a.revenue);
-
-        // By sales type
-        const stStats: Record<string, { name: string; platform: string; revenue: number; orders: number }> = {};
-        orders.forEach(o => {
-          const st = o.sales_type_id ? stMap.get(o.sales_type_id) : null;
-          const name = st ? st.name : "Standard";
-          const platform = st ? (platMap.get(st.platformId) ?? "Unknown") : "Direct";
-          const key = `${platform}-${name}`;
-          if (!stStats[key]) stStats[key] = { name, platform, revenue: 0, orders: 0 };
-          stStats[key].revenue += Number(o.subtotal ?? 0);
-          stStats[key].orders += 1;
-        });
-        const bySalesType = Object.values(stStats).sort((a, b) => b.revenue - a.revenue);
-
-        // By payment method
-        const pmStats: Record<string, number> = {};
-        orders.forEach(o => {
-          const pm = o.payment_method ?? "Not specified";
-          pmStats[pm] = (pmStats[pm] ?? 0) + Number(o.subtotal ?? 0);
-        });
-        const byPayment = Object.entries(pmStats).map(([name, amount]) => ({ name, amount })).sort((a, b) => b.amount - a.amount);
-
-        // Plant profitability
-        const filteredItems = items.filter(i => orderIds.has(i.order_id));
-        const varStats: Record<string, { name: string; stage: string; qtySold: number; revenue: number; cogs: number; grossProfit: number; netProfit: number; margin: number }> = {};
-        filteredItems.forEach(i => {
-          const key = `${i.variety_id}-${i.stage}`;
-          if (!varStats[key]) varStats[key] = { name: varMap.get(i.variety_id) ?? "Unknown", stage: i.stage, qtySold: 0, revenue: 0, cogs: 0, grossProfit: 0, netProfit: 0, margin: 0 };
-          varStats[key].qtySold += i.quantity ?? 0;
-          varStats[key].revenue += Number(i.line_total ?? 0);
-          varStats[key].cogs += Number(i.line_cogs ?? 0);
-          varStats[key].grossProfit += Number(i.line_profit ?? 0);
-          varStats[key].netProfit += Number(i.line_profit ?? 0);
-        });
-        Object.values(varStats).forEach(v => { v.margin = v.revenue > 0 ? (v.netProfit / v.revenue) * 100 : 0; });
-        const plantProfitability = Object.values(varStats).sort((a, b) => b.netProfit - a.netProfit);
-
-        return {
-          revenue, grossProfit, netProfit, totalCogs, shipping, adjTotal, avgOrderValue,
-          orderCount: orders.length, bestDay: bestDay ? { date: bestDay[0], amount: bestDay[1] } : null,
-          trend, byPlatform, bySalesType, byPayment, plantProfitability,
-          margin: revenue > 0 ? (netProfit / revenue) * 100 : 0,
-        };
-      };
-
-      return { current: calcStats(current), compare: compare.length > 0 ? calcStats(compare) : null };
-    },
-  });
-}
-
-export function useAnalyticsInventoryData() {
-  const { user } = useAuth();
-  return useQuery({
-    queryKey: ["analytics_inventory", user?.id],
-    enabled: !!user,
-    queryFn: async () => {
-      const [invRes, pricesRes, varietiesRes, catRes, lotAvgRes] = await Promise.all([
-        supabase.from("inventory").select("variety_id, stage, tier, quantity").eq("user_id", user!.id),
-        supabase.from("variety_stage_prices").select("variety_id, stage, tier, price").eq("user_id", user!.id),
-        supabase.from("plant_varieties").select("id, name, category_id").eq("user_id", user!.id),
-        supabase.from("plant_categories").select("id, name").eq("user_id", user!.id),
-        (supabase as any).from("inventory_lots_current_avg").select("variety_id, stage, tier, total_remaining, weighted_avg_cogs").eq("user_id", user!.id),
-      ]);
-
-      const inventory = invRes.data ?? [];
-      const prices = pricesRes.data ?? [];
-      const varMap = new Map((varietiesRes.data ?? []).map(v => [v.id, v]));
-      const catMap = new Map((catRes.data ?? []).map(c => [c.id, c.name]));
-      const lotAvgs = (lotAvgRes.data ?? []) as Array<{ variety_id: string; stage: string; tier: string | null; total_remaining: number; weighted_avg_cogs: number }>;
-      const lotKey = (vid: string, stage: string, tier: string | null) => `${vid}-${stage}-${tier ?? ""}`;
-      const lotAvgMap = new Map(lotAvgs.map(l => [lotKey(l.variety_id, l.stage, l.tier), Number(l.weighted_avg_cogs)]));
-
-      let totalPlants = 0, totalCogs = 0, totalSaleValue = 0;
-      const stageMap: Record<string, { quantity: number; value: number }> = {};
-      const categoryMap: Record<string, number> = {};
-      const breakdown: { variety: string; category: string; stage: string; tier: string; qty: number; avgCogs: number; totalCogs: number; suggestedPrice: number; estSaleValue: number; potentialProfit: number }[] = [];
-
-      for (const inv of inventory) {
-        const qty = inv.quantity ?? 0;
-        const lotAvg = lotAvgMap.get(lotKey(inv.variety_id, inv.stage, inv.tier ?? null)) ?? 0;
-        const cogs = qty * lotAvg;
-        const variety = varMap.get(inv.variety_id);
-        const catName = variety?.category_id ? catMap.get(variety.category_id) ?? "Uncategorized" : "Uncategorized";
-        const price = prices.find(p => p.variety_id === inv.variety_id && p.stage === inv.stage && ((p.tier ?? null) === (inv.tier ?? null)));
-        const saleVal = qty * Number(price?.price ?? 0);
-
-        totalPlants += qty;
-        totalCogs += cogs;
-        totalSaleValue += saleVal;
-
-        if (!stageMap[inv.stage]) stageMap[inv.stage] = { quantity: 0, value: 0 };
-        stageMap[inv.stage].quantity += qty;
-        stageMap[inv.stage].value += cogs;
-
-        categoryMap[catName] = (categoryMap[catName] ?? 0) + cogs;
-
-        if (qty > 0) {
-          breakdown.push({
-            variety: variety?.name ?? "Unknown", category: catName, stage: inv.stage, tier: inv.tier ?? "-",
-            qty, avgCogs: lotAvg, totalCogs: cogs,
-            suggestedPrice: Number(price?.price ?? 0), estSaleValue: saleVal, potentialProfit: saleVal - cogs,
-          });
-        }
-      }
-
-      const stages = STAGE_ORDER.map((s) => ({
-        stage: STAGE_LABELS[s],
-        quantity: stageMap[s]?.quantity ?? 0,
-        value: stageMap[s]?.value ?? 0,
-      }));
-
-      const byCategory = Object.entries(categoryMap).map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value);
-
-      return { totalPlants, totalCogs, totalSaleValue, potentialProfit: totalSaleValue - totalCogs, stages, byCategory, breakdown };
-    },
-  });
-}
-
-export function useAnalyticsExpensesData(range: DateRange, compareRange?: DateRange) {
-  const { user } = useAuth();
-  const from = fmt(range.from);
-  const to = fmt(range.to);
-  const cFrom = compareRange ? fmt(compareRange.from) : null;
-  const cTo = compareRange ? fmt(compareRange.to) : null;
-
-  return useQuery({
-    queryKey: ["analytics_expenses", user?.id, from, to, cFrom, cTo],
-    enabled: !!user,
-    queryFn: async () => {
-      const [expRes, ordersRes] = await Promise.all([
-        supabase.from("expenses").select("*").eq("user_id", user!.id),
-        supabase.from("orders").select("subtotal, sale_date, status, total_cogs").eq("user_id", user!.id).eq("status", "completed"),
-      ]);
-
-      const allExpenses = expRes.data ?? [];
-      const allOrders = ordersRes.data ?? [];
-
-      const calcExpStats = (f: string, t: string) => {
-        const expenses = allExpenses.filter(e => e.expense_date >= f && e.expense_date <= t);
-        const orders = allOrders.filter(o => o.sale_date >= f && o.sale_date <= t);
-        const total = expenses.reduce((s, e) => s + Number(e.amount), 0);
-        const recurring = expenses.filter(e => e.is_recurring).reduce((s, e) => s + Number(e.amount), 0);
-        const oneTime = total - recurring;
-        const revenue = orders.reduce((s, o) => s + Number(o.subtotal ?? 0), 0);
-        const expPctRevenue = revenue > 0 ? (total / revenue) * 100 : 0;
-
-        // Trend by month
-        const monthMap: Record<string, number> = {};
-        expenses.forEach(e => {
-          const m = e.expense_date.substring(0, 7);
-          monthMap[m] = (monthMap[m] ?? 0) + Number(e.amount);
-        });
-        const trend = Object.entries(monthMap).sort(([a], [b]) => a.localeCompare(b)).map(([month, amount]) => ({ month, amount }));
-
-        // By category
-        const catMap: Record<string, number> = {};
-        expenses.forEach(e => { catMap[e.category] = (catMap[e.category] ?? 0) + Number(e.amount); });
-        const byCategory = Object.entries(catMap).map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value);
-
-        // Overhead vs COGS vs Profit
-        const overheadCogs: Record<string, { expenses: number; cogs: number; profit: number }> = {};
-        expenses.forEach(e => {
-          const m = e.expense_date.substring(0, 7);
-          if (!overheadCogs[m]) overheadCogs[m] = { expenses: 0, cogs: 0, profit: 0 };
-          overheadCogs[m].expenses += Number(e.amount);
-        });
-        orders.forEach(o => {
-          const m = o.sale_date.substring(0, 7);
-          if (!overheadCogs[m]) overheadCogs[m] = { expenses: 0, cogs: 0, profit: 0 };
-          overheadCogs[m].cogs += Number(o.total_cogs ?? 0);
-          overheadCogs[m].profit += Number(o.subtotal ?? 0) - Number(o.total_cogs ?? 0);
-        });
-        const overheadVsCogs = Object.entries(overheadCogs).sort(([a], [b]) => a.localeCompare(b)).map(([month, v]) => ({ month, ...v }));
-
-        // Vendor summary
-        const vendorMap: Record<string, { total: number; count: number }> = {};
-        expenses.forEach(e => {
-          const v = e.vendor ?? "No Vendor";
-          if (!vendorMap[v]) vendorMap[v] = { total: 0, count: 0 };
-          vendorMap[v].total += Number(e.amount);
-          vendorMap[v].count += 1;
-        });
-        const vendorSummary = Object.entries(vendorMap).map(([name, v]) => ({ name, ...v })).sort((a, b) => b.total - a.total);
-
-        // Detail table
-        const detail = expenses.map(e => ({
-          date: e.expense_date, name: e.name, category: e.category, taxCategory: e.tax_category ?? "-",
-          vendor: e.vendor ?? "-", amount: Number(e.amount), recurring: e.is_recurring ? (e.frequency ?? "Yes") : "No",
-        })).sort((a, b) => b.date.localeCompare(a.date));
-
-        return { total, recurring, oneTime, expPctRevenue, trend, byCategory, overheadVsCogs, vendorSummary, detail };
-      };
-
-      const current = calcExpStats(from, to);
-      const compare = cFrom && cTo ? calcExpStats(cFrom, cTo) : null;
-
-      return { current, compare };
-    },
-  });
-}
-
-export function useAnalyticsSuppliersData() {
-  const { user } = useAuth();
-  return useQuery({
-    queryKey: ["analytics_suppliers", user?.id],
-    enabled: !!user,
-    queryFn: async () => {
-      const [suppRes, poRes, poiRes, lossRes, varRes] = await Promise.all([
-        supabase.from("suppliers").select("id, name").eq("user_id", user!.id),
-        supabase.from("purchase_orders").select("id, supplier_id, flight_date, received_date, condition_rating, status").eq("user_id", user!.id),
-        supabase.from("purchase_order_items").select("purchase_order_id, variety_id, quantity_ordered, quantity_received, qty_doa, qty_damaged, qty_missing").eq("user_id", user!.id),
-        supabase.from("plant_losses").select("variety_id, supplier_id, quantity_lost, loss_type, loss_date, cogs_value_lost").eq("user_id", user!.id),
-        supabase.from("plant_varieties").select("id, name").eq("user_id", user!.id),
-      ]);
-
-      const suppliers = suppRes.data ?? [];
-      const pos = poRes.data ?? [];
-      const pois = poiRes.data ?? [];
-      const losses = lossRes.data ?? [];
-      const varMap = new Map((varRes.data ?? []).map(v => [v.id, v.name]));
-
-      const suppMap = new Map(suppliers.map(s => [s.id, s.name]));
-      const poSupplier = new Map(pos.map(po => [po.id, po.supplier_id]));
-
-      // Supplier performance
-      const perfMap: Record<string, {
-        name: string; orders: number; purchased: number; ordered: number; lost: number; doa: number;
-        cogsLost: number; conditionSum: number; conditionCount: number;
-        flightDays: number[]; lossTypes: Record<string, number>;
-      }> = {};
-
-      const getPerf = (sid: string) => {
-        if (!perfMap[sid]) perfMap[sid] = {
-          name: suppMap.get(sid) ?? "Unknown", orders: 0, purchased: 0, ordered: 0, lost: 0, doa: 0,
-          cogsLost: 0, conditionSum: 0, conditionCount: 0, flightDays: [], lossTypes: {},
-        };
-        return perfMap[sid];
-      };
-
-      pos.forEach(po => {
-        const p = getPerf(po.supplier_id);
-        p.orders += 1;
-        if (po.condition_rating) {
-          const rating = parseInt(po.condition_rating);
-          if (!isNaN(rating)) { p.conditionSum += rating; p.conditionCount += 1; }
-        }
-        if (po.flight_date && po.received_date) {
-          const days = Math.abs(new Date(po.received_date).getTime() - new Date(po.flight_date).getTime()) / 86400000;
-          p.flightDays.push(Math.round(days));
-        }
-      });
-
-      pois.forEach(poi => {
-        const sid = poSupplier.get(poi.purchase_order_id);
-        if (!sid) return;
-        const p = getPerf(sid);
-        p.purchased += poi.quantity_received ?? poi.quantity_ordered ?? 0;
-        p.ordered += poi.quantity_ordered ?? 0;
-        p.doa += poi.qty_doa ?? 0;
-      });
-
-      losses.forEach(l => {
-        if (!l.supplier_id) return;
-        const p = getPerf(l.supplier_id);
-        p.lost += l.quantity_lost;
-        p.cogsLost += Number(l.cogs_value_lost ?? 0);
-        p.lossTypes[l.loss_type] = (p.lossTypes[l.loss_type] ?? 0) + l.quantity_lost;
-      });
-
-      const performance = Object.entries(perfMap).map(([id, p]) => ({
-        id, name: p.name, orders: p.orders, purchased: p.purchased, lost: p.lost,
-        survivalRate: p.ordered > 0 ? ((p.ordered - p.lost) / p.ordered) * 100 : 100,
-        doaRate: p.ordered > 0 ? (p.doa / p.ordered) * 100 : 0,
-        avgCondition: p.conditionCount > 0 ? p.conditionSum / p.conditionCount : 0,
-        avgFlightDays: p.flightDays.length > 0 ? p.flightDays.reduce((a, b) => a + b, 0) / p.flightDays.length : 0,
-        fastestFlight: p.flightDays.length > 0 ? Math.min(...p.flightDays) : 0,
-        slowestFlight: p.flightDays.length > 0 ? Math.max(...p.flightDays) : 0,
-        flightCount: p.flightDays.length,
-        cogsLost: p.cogsLost, lossTypes: p.lossTypes,
-      })).sort((a, b) => b.survivalRate - a.survivalRate);
-
-      // Survival by variety per supplier
-      const svMap: Record<string, { supplier: string; variety: string; purchased: number; lost: number }> = {};
-      pois.forEach(poi => {
-        const sid = poSupplier.get(poi.purchase_order_id);
-        if (!sid) return;
-        const key = `${sid}-${poi.variety_id}`;
-        if (!svMap[key]) svMap[key] = { supplier: suppMap.get(sid) ?? "Unknown", variety: varMap.get(poi.variety_id) ?? "Unknown", purchased: 0, lost: 0 };
-        svMap[key].purchased += poi.quantity_received ?? poi.quantity_ordered ?? 0;
-      });
-      losses.forEach(l => {
-        if (!l.supplier_id) return;
-        const key = `${l.supplier_id}-${l.variety_id}`;
-        if (svMap[key]) svMap[key].lost += l.quantity_lost;
-      });
-      const varietySurvival = Object.values(svMap).map(v => ({
-        ...v, survivalRate: v.purchased > 0 ? ((v.purchased - v.lost) / v.purchased) * 100 : 100,
-      })).sort((a, b) => a.survivalRate - b.survivalRate);
-
-      const totalPurchased = performance.reduce((s, p) => s + p.purchased, 0);
-      const totalLost = performance.reduce((s, p) => s + p.lost, 0);
-      const overallSurvival = totalPurchased > 0 ? ((totalPurchased - totalLost) / totalPurchased) * 100 : 100;
-
-      return { performance, varietySurvival, totalSuppliers: suppliers.length, totalPurchased, totalLost, overallSurvival };
-    },
-  });
-}
diff --git a/src/pages/Analytics.tsx b/src/pages/Analytics.tsx
index 6b770fc..9bad13e 100644
--- a/src/pages/Analytics.tsx
+++ b/src/pages/Analytics.tsx
@@ -9,10 +9,14 @@ import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover
 import { Calendar } from "@/components/ui/calendar";
 import { format } from "date-fns";
 import { CalendarIcon } from "lucide-react";
-import {
-  AnalyticsPeriod, getAnalyticsDateRange, DateRange,
-  useAnalyticsSalesData, useAnalyticsInventoryData, useAnalyticsExpensesData, useAnalyticsSuppliersData, useGoals,
-} from "@/hooks/useAnalyticsData";
+import type { AnalyticsPeriod } from "@/hooks/AnalyticsPeriod";
+import type { DateRange } from "@/hooks/DateRange";
+import { getAnalyticsDateRange } from "@/hooks/getAnalyticsDateRange";
+import { useAnalyticsSalesData } from "@/hooks/useAnalyticsSalesData";
+import { useAnalyticsInventoryData } from "@/hooks/useAnalyticsInventoryData";
+import { useAnalyticsExpensesData } from "@/hooks/useAnalyticsExpensesData";
+import { useAnalyticsSuppliersData } from "@/hooks/useAnalyticsSuppliersData";
+import { useGoals } from "@/hooks/useGoals";
 import { GoalsSection } from "@/components/analytics/GoalsSection";
 import { SalesSection } from "@/components/analytics/SalesSection";
 import { ProfitSection } from "@/components/analytics/ProfitSection";
```

- Merged JediBranch/oneExportPerFile/210725-20260509/useAnalyticsData → JediBranch/oneExportPerFile/210725-20260509/base (sha: f62deda1d6285d96ba951e57051f3777be7669a2)
- Done with useAnalyticsData.ts.
- Returned to original branch: main

## Summary

- total_files: 5
- skipped: 1
- split: 4
- merged: 4
- errors: 0
- opencode_used: 4
- opencode_used: 4
