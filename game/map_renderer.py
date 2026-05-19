import folium
from folium.plugins import AntPath
from game.models import Player, Treasure
from typing import List

CATEGORY_ICONS = {
    "cafe":       ("orange", "coffee"),
    "museum":     ("purple", "university"),
    "park":       ("green",  "tree"),
    "library":    ("blue",   "book"),
    "restaurant": ("red",    "cutlery"),
}


def render_game_map(player: Player, treasures: List[Treasure],
                    optimal_route: List[Treasure], route_coords: list) -> str:
    m = folium.Map(location=player.coords, zoom_start=15, tiles="OpenStreetMap")

    folium.Marker(
        location=player.coords,
        popup=folium.Popup(f"<b>🧭 起點</b><br>玩家: {player.name}", max_width=200),
        icon=folium.Icon(color="blue", icon="home", prefix="fa"),
        tooltip="你的起點"
    ).add_to(m)

    for treasure in treasures:
        color, icon = CATEGORY_ICONS.get(treasure.category, ("gray", "star"))
        order = next((j+1 for j, t in enumerate(optimal_route) if t.id == treasure.id), "?")
        btn_html = (
            "<p style='color:#34a853;font-weight:bold'>✅ 已收集</p>"
            if treasure.found else
            f"<button onclick=\"window.parent.collect('{treasure.id}')\" "
            f"style='margin-top:6px;padding:6px 14px;background:#1a73e8;color:white;"
            f"border:none;border-radius:6px;cursor:pointer;font-size:13px'>✅ 收集寶藏</button>"
        )
        popup_html = f"""
        <div style='font-family:Arial;min-width:160px;padding:4px'>
            <h4 style='margin:0 0 6px'>{'✅' if treasure.found else '💎'} {treasure.name}</h4>
            <p style='margin:2px 0;font-size:12px;color:#555'>類別: {treasure.category}</p>
            <p style='margin:2px 0;font-size:13px'>分數: <b style='color:#e8a000'>{treasure.points} 分</b></p>
            <p style='margin:2px 0;font-size:12px;color:#555'>建議第 {order} 個收集</p>
            {btn_html}
        </div>
        """
        folium.Marker(
            location=treasure.coords,
            popup=folium.Popup(popup_html, max_width=240),
            icon=folium.Icon(color="lightgray" if treasure.found else color, icon=icon, prefix="fa"),
            tooltip=f"{'✅ 已收集' if treasure.found else '💎 點擊收集'} {treasure.name} ({treasure.points}分)"
        ).add_to(m)

        folium.Marker(
            location=treasure.coords,
            icon=folium.DivIcon(
                html=f'<div style="font-size:12px;font-weight:bold;color:white;'
                     f'background:#333;border-radius:50%;width:20px;height:20px;'
                     f'text-align:center;line-height:20px;">{order}</div>',
                icon_size=(20, 20), icon_anchor=(10, 10)
            )
        ).add_to(m)

    if route_coords:
        coords_latlon = [[c[1], c[0]] for c in route_coords]
        AntPath(locations=coords_latlon, color="#E74C3C", weight=4, tooltip="最優尋寶路線").add_to(m)
    else:
        line_coords = [player.coords] + [t.coords for t in optimal_route]
        folium.PolyLine(locations=line_coords, color="#E74C3C", weight=3, dash_array="10").add_to(m)

    legend_html = """
    <div style='position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:10px;border-radius:8px;border:2px solid #ccc;font-size:13px'>
        <b>圖例</b><br>
        🏠 起點 &nbsp; 💎 未找到 &nbsp; ✅ 已找到<br>
        <span style='color:#E74C3C'>─── </span>最優路線
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    return m._repr_html_()
