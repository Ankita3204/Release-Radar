"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { apiSend } from "@/lib/api-client";

export function LogoutButton({ csrf }: { csrf: string }) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      variant="outline"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await apiSend("/v1/auth/logout", "POST", csrf);
        } finally {
          window.location.assign("/login");
        }
      }}
    >
      Sign out
    </Button>
  );
}
