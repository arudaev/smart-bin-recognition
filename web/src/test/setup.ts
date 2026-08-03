/* Test setup, deliberately almost empty.

   Most of what is worth testing here has no DOM in it: the resolver, the gates,
   the wire format, the metrics ring buffer, the geohash. Those run in node and
   should keep running in node, because a suite that needs a browser to check a
   pure function is a suite people stop running.

   What does belong here is the handful of build-time constants that vite
   substitutes and vitest does not, since a module that reads them would
   otherwise throw a ReferenceError in a test that had nothing to do with them. */

const globals = globalThis as Record<string, unknown>;

globals.__APP_VERSION__ ??= "0.0.0-test";
globals.__BUILD_TIME__ ??= "1970-01-01";
