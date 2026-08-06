import { useCallback, useEffect, useState } from "react";

/* The React half of the router, and all of it.
 *
 * routes.ts holds the policy and is tested without a browser; this holds the
 * two lines of platform that policy needs – read the address bar, listen for
 * the back button – and nothing else.
 *
 * pushState for a place the user chose to go, replaceState for a correction
 * they did not. A redirect written with pushState leaves the wrong URL in the
 * history stack and the back button bounces straight off it again.
 */

export interface Router {
  path: string;
  navigate: (to: string, options?: { replace?: boolean }) => void;
}

function currentPath(): string {
  if (typeof window === "undefined") return "/";
  return window.location.pathname;
}

export function useRouter(): Router {
  const [path, setPath] = useState(currentPath);

  useEffect(() => {
    const onPop = () => setPath(currentPath());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = useCallback((to: string, options?: { replace?: boolean }) => {
    if (typeof window !== "undefined" && currentPath() !== to) {
      // History entries carry no state of their own. Everything the shell needs
      // is in the path, which is what makes a cold launch and a back button
      // arrive at the same screen.
      if (options?.replace) window.history.replaceState(null, "", to);
      else window.history.pushState(null, "", to);
    }
    setPath(to);
  }, []);

  return { path, navigate };
}
