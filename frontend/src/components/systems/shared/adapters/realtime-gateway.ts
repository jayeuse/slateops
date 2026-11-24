import { RealtimeClient } from "@supabase/realtime-js";

/**
 * A Realtime client on the same-origin gateway (`/realtime/v1`). The SDK
 * needs a nonempty key to start; this noncredential marker is removed by
 * its documented transport seam, and only the gateway adds the real key.
 * Comms and sheet presence each open their own client: a client carries one
 * access token, and a sheet's presence connection carries no OpenComms
 * channel (docs/specs/sheets.md D13).
 */
export function createGatewayRealtime(): RealtimeClient {
  const endpoint = new URL("/realtime/v1", globalThis.location.href);
  endpoint.protocol = endpoint.protocol === "https:" ? "wss:" : "ws:";
  class GatewaySocket extends WebSocket {
    constructor(address: string | URL, protocols?: string | string[]) {
      const target = new URL(address);
      if (
        target.origin !== endpoint.origin ||
        target.pathname !== "/realtime/v1/websocket" ||
        target.searchParams.get("apikey") !== "gateway-header"
      )
        throw new Error("Invalid Realtime transport target");
      target.searchParams.delete("apikey");
      if (
        [...target.searchParams.keys()].some((key) => key !== "vsn") ||
        target.searchParams.get("vsn") !== "1.0.0"
      )
        throw new Error("Invalid Realtime transport parameters");
      super(target, protocols);
    }
  }
  return new RealtimeClient(endpoint.href, {
    transport: GatewaySocket,
    params: { apikey: "gateway-header" },
    vsn: "1.0.0",
  });
}
