# DeltaBot React Frontend Enhancement: Adaptive Strategy Dashboard

Modify the existing DeltaBot React frontend only. Do not create a new frontend project, replace routing, or change the visual design language. Reuse existing API clients, WebSocket handling, cards, charts, controls, layout, authentication, paper/live switch, and position components wherever they already exist.

Add an **Adaptive Strategy Dashboard** to the existing trading view (or the closest existing strategy page). It must consume the existing WebSocket `MARKET_UPDATE` payload's `adaptiveStrategy` field and fall back to `GET /api/adaptive-strategy/status` on first load/reconnect.

Display:

- Market regime, confidence, and analysis reasons.
- Selected strategy, entry/entry-rejection reason, and per-strategy scores.
- Current adaptive position, live P&L, grouped legs, Greeks, delta exposure, and margin usage.
- Active risk limits and their current utilisation.
- Time series charts for BTC price, IV, ATR, ADX, and funding rate. Use existing chart components and preserve their styling.

Add controls using the existing form/button patterns:

- Start/stop adaptive trading via `POST /api/adaptive-strategy/enable` and `POST /api/adaptive-strategy/disable`.
- Optional close-on-stop with `close_active=true`.
- Per-strategy enable/disable using `POST /api/adaptive-strategy/{strategy_name}/enabled?enabled=true|false`.
- Risk-limit and expiry-preference editors wired to the application's existing configuration/settings API if present. If no settings API exists, render them read-only with a clear “server-configured” label; do not invent a persistence backend.
- Preserve the current Paper Trading / Live Trading switch—never add a second mode control if one already exists.

Handle `disabled`, `no_trade`, `risk_rejected`, `entry_rejected`, `executed`, and `monitoring` states explicitly. Empty/unknown data must show a calm, actionable no-trade state, not an error. Keep strategy names exactly as returned by the API. Do not change existing endpoints or break current strategy controls.
