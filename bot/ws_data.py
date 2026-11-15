import asyncio
import json
import aiohttp
import time
from typing import Optional, Dict, List
from .net_utils import get_proxy_url_for


class PolymarketClobMarketStream:
    """Real-time orderbook and price feed for active Polymarket tokens over CLOB Market WS."""
    def __init__(self, ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"):
        self.ws_url = ws_url
        self.asset_ids: List[str] = []
        self.books: Dict[str, Dict] = {}  # asset_id -> {"bids": [...], "asks": [...], "best_bid": float, "best_ask": float}
        self.book_levels: Dict[str, Dict[str, Dict[float, float]]] = {}  # asset_id -> {"bids": {px: sz}, "asks": {px: sz}}
        self.last_ts: float = 0
        self.closed = False
        self._ws = None

    def update_assets(self, asset_ids: List[str]):
        new_ids = sorted(list(set(asset_ids)))
        if new_ids != self.asset_ids:
            self.asset_ids = new_ids
            if self._ws and not self._ws.closed and self.asset_ids:
                asyncio.create_task(self._subscribe(self._ws))

    async def _subscribe(self, ws):
        if not self.asset_ids:
            return
        sub_msg = {
            "assets_ids": self.asset_ids,
            "type": "market"
        }
        try:
            await ws.send_json(sub_msg)
            print(f"Subscribed to Polymarket CLOB Market WS for tokens: {self.asset_ids}")
        except Exception as e:
            print(f"Failed to subscribe to CLOB market WS: {e}")

    async def start(self):
        async def ping_loop(ws):
            while not self.closed:
                try:
                    await asyncio.sleep(10)
                    if not ws.closed:
                        await ws.send_str("PING")
                except Exception:
                    break

        while not self.closed:
            try:
                proxy = get_proxy_url_for(self.ws_url)
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(self.ws_url, proxy=proxy if proxy else None) as ws:
                        self._ws = ws
                        print(f"Connected to Polymarket CLOB Market WS: {self.ws_url}")
                        await self._subscribe(ws)
                        ping_task = asyncio.create_task(ping_loop(ws))

                        try:
                            while not self.closed:
                                msg = await ws.receive()
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    data_text = msg.data.strip() if msg.data else ""
                                    if not data_text or data_text in ("PONG", "PING", "OK", "PONG\n"):
                                        continue
                                    try:
                                        data = json.loads(data_text)
                                        self._process_msg(data)
                                    except Exception:
                                        continue
                                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                    break
                        finally:
                            ping_task.cancel()
            except Exception as e:
                print(f"Polymarket CLOB Market WS error: {e}")
                if not self.closed:
                    await asyncio.sleep(2)

    def _sync_book_entry(self, aid: str):
        levels = self.book_levels.get(aid, {"bids": {}, "asks": {}})
        bids_map = levels.get("bids", {})
        asks_map = levels.get("asks", {})

        # Bids: descending by price (highest bid first)
        sorted_bids = sorted(
            [{"price": f"{p:.4f}", "size": s, "px": p} for p, s in bids_map.items() if s > 0],
            key=lambda x: x["px"],
            reverse=True
        )
        # Asks: ascending by price (lowest ask first)
        sorted_asks = sorted(
            [{"price": f"{p:.4f}", "size": s, "px": p} for p, s in asks_map.items() if s > 0],
            key=lambda x: x["px"]
        )

        best_bid = sorted_bids[0]["px"] if sorted_bids else None
        best_ask = sorted_asks[0]["px"] if sorted_asks else None

        self.books[aid] = {
            "bids": sorted_bids,
            "asks": sorted_asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "updated_at": self.last_ts
        }

    def _process_msg(self, data):
        self.last_ts = time.time()
        # Single book dict snapshot
        if isinstance(data, dict) and ("bids" in data or "asks" in data or data.get("event_type") in ("book", "market")):
            aid = str(data.get("asset_id") or data.get("market") or "")
            if aid:
                levels = self.book_levels.setdefault(aid, {"bids": {}, "asks": {}})
                if "bids" in data:
                    levels["bids"] = {}
                    for b in data.get("bids", []):
                        try:
                            levels["bids"][float(b["price"])] = float(b.get("size", 0))
                        except (TypeError, ValueError, KeyError):
                            pass
                if "asks" in data:
                    levels["asks"] = {}
                    for a in data.get("asks", []):
                        try:
                            levels["asks"][float(a["price"])] = float(a.get("size", 0))
                        except (TypeError, ValueError, KeyError):
                            pass
                self._sync_book_entry(aid)
                if data.get("best_bid") is not None:
                    try:
                        self.books[aid]["best_bid"] = float(data["best_bid"])
                    except Exception:
                        pass
                if data.get("best_ask") is not None:
                    try:
                        self.books[aid]["best_ask"] = float(data["best_ask"])
                    except Exception:
                        pass

        # Full book snapshot (list)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "asset_id" in item:
                    aid = str(item["asset_id"])
                    levels = self.book_levels.setdefault(aid, {"bids": {}, "asks": {}})
                    levels["bids"] = {}
                    levels["asks"] = {}
                    for b in item.get("bids", []):
                        try:
                            levels["bids"][float(b["price"])] = float(b.get("size", 0))
                        except (TypeError, ValueError, KeyError):
                            pass
                    for a in item.get("asks", []):
                        try:
                            levels["asks"][float(a["price"])] = float(a.get("size", 0))
                        except (TypeError, ValueError, KeyError):
                            pass
                    self._sync_book_entry(aid)
                    if item.get("best_bid") is not None:
                        try:
                            self.books[aid]["best_bid"] = float(item["best_bid"])
                        except Exception:
                            pass
                    if item.get("best_ask") is not None:
                        try:
                            self.books[aid]["best_ask"] = float(item["best_ask"])
                        except Exception:
                            pass

        # Price / book delta updates
        elif isinstance(data, dict):
            price_changes = data.get("price_changes") or data.get("changes") or []
            if isinstance(price_changes, list):
                for pc in price_changes:
                    if not isinstance(pc, dict):
                        continue
                    aid = str(pc.get("asset_id") or data.get("asset_id") or "")
                    if not aid:
                        continue
                    levels = self.book_levels.setdefault(aid, {"bids": {}, "asks": {}})
                    side = str(pc.get("side", "")).upper()
                    try:
                        p = float(pc["price"])
                        s = float(pc.get("size", 0))
                        if side == "BUY":
                            if s > 0:
                                levels["bids"][p] = s
                            else:
                                levels["bids"].pop(p, None)
                        elif side == "SELL":
                            if s > 0:
                                levels["asks"][p] = s
                            else:
                                levels["asks"].pop(p, None)
                    except (TypeError, ValueError, KeyError):
                        pass

                    self._sync_book_entry(aid)
                    if pc.get("best_bid") is not None:
                        try:
                            self.books[aid]["best_bid"] = float(pc["best_bid"])
                        except (TypeError, ValueError):
                            pass
                    if pc.get("best_ask") is not None:
                        try:
                            self.books[aid]["best_ask"] = float(pc["best_ask"])
                        except (TypeError, ValueError):
                            pass

            aid = str(data.get("asset_id") or "")
            if aid:
                if aid in self.books:
                    self.books[aid]["updated_at"] = self.last_ts
                    if data.get("best_bid") is not None:
                        try:
                            self.books[aid]["best_bid"] = float(data["best_bid"])
                        except (TypeError, ValueError):
                            pass
                    if data.get("best_ask") is not None:
                        try:
                            self.books[aid]["best_ask"] = float(data["best_ask"])
                        except (TypeError, ValueError):
                            pass

    def get_token_market(self, asset_id: str) -> Dict:
        return self.books.get(str(asset_id), {})

    def get_summary(self, asset_id: str, max_age_s: float = 5.0) -> Optional[Dict]:
        """Return best bid/ask, spread, liquidity and bids list for `asset_id` if fresh."""
        aid = str(asset_id)
        book = self.books.get(aid)
        if not book:
            return None
        updated_at = book.get("updated_at", 0)
        if max_age_s > 0 and (time.time() - updated_at) > max_age_s:
            return None
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        best_bid = book.get("best_bid")
        best_ask = book.get("best_ask")

        if best_bid is None and bids:
            try:
                best_bid = float(bids[0].get("px", bids[0]["price"]))
            except Exception:
                pass
        if best_ask is None and asks:
            try:
                best_ask = float(asks[0].get("px", asks[0]["price"]))
            except Exception:
                pass

        spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None

        bid_liq = 0.0
        for b in bids[:5]:
            try:
                bid_liq += float(b.get("size", 0))
            except Exception:
                pass

        ask_liq = 0.0
        for a in asks[:5]:
            try:
                ask_liq += float(a.get("size", 0))
            except Exception:
                pass

        return {
            "bestBid": best_bid,
            "bestAsk": best_ask,
            "spread": spread,
            "bidLiquidity": bid_liq,
            "askLiquidity": ask_liq,
            "bids": bids,
            "asks": asks,
            "updated_at": updated_at
        }

    def close(self):
        self.closed = True
