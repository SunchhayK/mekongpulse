import { createNavigation } from "next-intl/navigation";
import { routing } from "./routing";

// Lightweight wrappers around Next.js' navigation APIs that account for the
// locale prefix (/km, /en). Works with the static export: every locale route
// is pre-rendered, so client-side navigation stays within the bundle.
export const { Link, redirect, usePathname, useRouter, getPathname } =
  createNavigation(routing);
