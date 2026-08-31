"""Map-Viewer: zeichnet die Arena, Kamera frei bewegbar. Keine Spiellogik."""
import os
import random

import pygame

from .settings import TILE, MAP_W, MAP_H, VIEW_W, VIEW_H, FPS, C_BG
from . import paths
from . import mapgen
from . import theme
from .menu import Menu
from .world import World

PAN_SPEED = 260.0          # Pixel pro Sekunde
PAN_FAST = 720.0

# Zifferntasten waehlen die Gruppe - erneutes Druecken geht darin weiter.
_GRUPPENTASTEN = {
    pygame.K_1: "Arena", pygame.K_KP_1: "Arena",
    pygame.K_2: "Dungeon", pygame.K_KP_2: "Dungeon",
    pygame.K_3: "Organisch", pygame.K_KP_3: "Organisch",
    pygame.K_4: "Labyrinth", pygame.K_KP_4: "Labyrinth",
}


class Viewer:
    def __init__(self, seed=None, mode=None, size=None, safe=None,
                 ecke="oben links", masse=None):
        pygame.init()
        pygame.display.set_caption("Arena - Map Viewer")

        info = pygame.display.Info()
        self.scale = max(1, min(info.current_w // VIEW_W,
                                (info.current_h - 90) // VIEW_H))
        self.scale = max(2, min(self.scale, 4))
        self.fullscreen = False
        self._scaled = False
        if not self._set_mode():
            raise SystemExit(
                "Kein Anzeigefenster moeglich - SDL konnte keinen Renderer\n"
                "aufbauen. Meist hilft ein Grafiktreiber-Update; sonst\n"
                "laeuft der Export auch ohne Fenster:\n"
                "    python main.py --seed 4242 --export")

        # Ohne Wiederholung muss jede Ziffer und jede Rueckschritttaste
        # einzeln angeschlagen werden - in einem Textfeld ist das falsch.
        pygame.key.set_repeat(400, 40)
        self.clock = pygame.time.Clock()
        self.view = pygame.Surface((VIEW_W, VIEW_H)).convert()
        self.seed = seed
        self.mode = mode
        self.size = size
        self.safe = safe            # Name aus mapgen.SAFE_SIZES, oder None
        self.ecke = ecke
        self.masse = masse          # eigene Kartenmasse, oder None
        self.safe_masse = None      # eigene Startraummasse, oder None
        self.world = World(seed, mode, size, self._safe_size(), ecke, masse)
        self.menu = None
        self._update_url = None
        e = paths.load_settings()
        self.export_dir = e["export"]
        self.theme_name = e["theme"] if e["theme"] in theme.NAMEN else "dunkel"
        self.hud_name = (e["hud"] if e["hud"] in theme.GROESSEN_NAMEN
                         else "normal")
        self.status = ""
        self.status_t = 0.0

        self.cam = [0.0, 0.0]
        self._fit_camera()
        self.overview = False
        self.show_help = True
        self.show_grid = False
        self.show_spawns = True
        self.running = True

    # ------------------------------------------------------------ Karte
    def load(self, seed):
        """Karte neu bauen. `seed=None` heisst: handgesetztes Layout."""
        self.seed = seed
        self.world = World(seed, self.mode, self.size, self._safe_size(),
                           self.ecke, self.masse)
        self._fit_camera()
        bp = self.world.blueprint
        if bp is None:
            self.flash("Handgesetztes Layout")
        else:
            self.flash("%s%s (%s) - Seed %d - %d%% offen"
                       % ("" if self.size is None else "%dx%d " % (bp.w, bp.h),
                          bp.mode, bp.group, bp.seed,
                          round(bp.open_ratio * 100)))

    def jump_group(self, gruppe):
        """Zur ersten Art einer Gruppe springen, bei gleichem Seed.

        `TAB` laeuft alle sechsundzwanzig der Reihe nach durch; wer von
        einer Hoehle zu einem Dungeon will, drueckt sonst ein Dutzend Mal.
        """
        arten = [n for n in mapgen.MODE_NAMES
                 if mapgen.MODES[n]["gruppe"] == gruppe]
        if not arten:
            return
        # Steht man schon in der Gruppe, geht es eine Art weiter.
        if self.mode in arten:
            self.mode = arten[(arten.index(self.mode) + 1) % len(arten)]
        else:
            self.mode = arten[0]
        self.load(self.seed if self.seed is not None else 1)

    # ----------------------------------------------------------- Anzeige
    @property
    def T(self):
        """Farben des gewaehlten Schemas."""
        return theme.farben(self.theme_name)

    @property
    def hs(self):
        """Schriftgroesse: Fensterskalierung mal HUD-Faktor.

        Als eigene Groesse und nicht `self.scale`: die Fensterskalierung
        haengt am Bildschirm, die Schriftgroesse am Geschmack. Beides in
        einer Zahl liesse sich nur eins von beidem einstellen.
        """
        return self.scale * theme.faktor(self.hud_name)

    def _safe_size(self):
        if self.safe == "eigene":
            return self.safe_masse
        return mapgen.SAFE_SIZES.get(self.safe) if self.safe else None

    def cycle_mode(self, step):
        """Eine Art weiter, bei gleichem Seed.

        Denselben Seed zu behalten ist der Punkt: so vergleicht man die
        Arten am selben Grundriss und nicht an zwei fremden Karten.
        """
        names = mapgen.MODE_NAMES
        if self.mode in names:
            i = (names.index(self.mode) + step) % len(names)
        else:
            i = 0 if step > 0 else len(names) - 1
        self.mode = names[i]
        self.load(self.seed if self.seed is not None else 1)

    def _menu_key(self, ev):
        """Eine Taste im Menue. Gibt zurueck, ob sie verbraucht wurde."""
        m = self.menu
        # In jeder Textfeldzeile sind Ziffern Eingabe, nicht Kuerzel.
        f = m.feld()
        if f is not None:
            strg = ev.mod & pygame.KMOD_CTRL
            if strg and ev.key == pygame.K_v:
                f.paste()
                return True
            if strg and ev.key == pygame.K_a:
                f.clear()
                return True
            if ev.unicode.isdigit():
                f.insert(ev.unicode)
                return True
            if ev.key == pygame.K_BACKSPACE:
                f.backspace()
                return True
            if ev.key == pygame.K_DELETE:
                f.delete()
                return True
            if ev.key == pygame.K_HOME:
                f.home()
                return True
            if ev.key == pygame.K_END:
                f.end()
                return True
            if ev.key in (pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS):
                m.step(1)
                return True
            if ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                m.step(-1)
                return True
        if ev.key in (pygame.K_ESCAPE, pygame.K_F1, pygame.K_F2):
            self.menu = None
        elif ev.key == pygame.K_UP:
            m.move(-1)
        elif ev.key == pygame.K_DOWN:
            m.move(1)
        elif ev.key in (pygame.K_LEFT, pygame.K_RIGHT):
            m.change(-1 if ev.key == pygame.K_LEFT else 1)
            # Schrift und Farbe wirken sofort - man will sehen, was man
            # waehlt, nicht erst nach dem naechsten Kartenbau.
            if m.aktiv() in ("hud", "schema"):
                self.hud_name, self.theme_name = m.hud, m.schema
                paths.save_settings(hud=m.hud, theme=m.schema)
        elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            key = m.aktiv()
            if key == "ordner":
                self.choose_dir()
            elif key == "update":
                self.update_schritt()
            else:
                self.apply_menu()
        else:
            return False
        return True

    def update_schritt(self):
        """Erst pruefen, beim zweiten ENTER installieren.

        Zwei Schritte mit Absicht: ein Druck auf ENTER soll nicht
        unversehens das Programm austauschen. Was gefunden wurde, steht
        vorher in der Zeile.
        """
        from . import update as U
        if self._update_url:
            self.menu.update_text = "laedt ..."
            self.draw_scene()
            self.draw_hud()
            pygame.display.flip()
            try:
                neu = os.path.join(os.path.dirname(os.path.abspath(
                    __import__("sys").executable)), "ArenaMapTool.neu.exe")
                U.lade(self._update_url, neu)
                U.tausche_und_starte(neu)
                self.flash("Update wird eingespielt - Programm startet neu")
                self.running = False
            except Exception as err:
                self.menu.update_text = "fehlgeschlagen: %s" % err
                self._update_url = None
            return

        self.menu.update_text = "pruefe ..."
        self.draw_scene()
        self.draw_hud()
        pygame.display.flip()
        zustand, text, ver, url = U.pruefe()
        if zustand == "neu" and paths.frozen():
            self._update_url = url
            self.menu.update_text = "%s - ENTER installiert" % ver
        else:
            self._update_url = None
            self.menu.update_text = (text if zustand != "neu"
                                     else "%s - nur die .exe kann das" % ver)

    def choose_dir(self):
        """Zielordner auswaehlen und merken.

        Der Dialog blockiert den Viewer, solange er offen ist - das ist
        bei einer Ordnerauswahl richtig so. Bricht der Benutzer ab oder
        fehlt tkinter, bleibt der bisherige Ordner stehen.
        """
        neu = paths.waehle_ordner(self.export_dir)
        if not neu:
            self.flash("Ordner unveraendert")
            return
        self.export_dir = os.path.normpath(neu)
        self.menu.export_dir = self.export_dir
        if paths.save_output(self.export_dir):
            self.flash("Export nach %s" % paths.kuerzen(self.export_dir, 40))
        else:
            self.flash("Ordner gesetzt, aber nicht merkbar")

    def _menu_click(self, pos):
        """Menuezeile anklicken; im Seedfeld auch die Schreibmarke setzen."""
        for i, rect in enumerate(getattr(self, "_menu_rects", [])):
            if not rect.collidepoint(pos):
                continue
            self.menu.row = i
            key = self.menu.aktiv()
            f = self.menu.feld(key)
            if f is not None:
                schrift = self.font(int(8 * self.scale), True)
                f.caret_from_x(pos[0] - self._menu_text_x,
                               lambda n: schrift.size(f.text[:n])[0])
            elif key == "ordner":
                self.choose_dir()
            return

    def apply_menu(self):
        """Einstellungen uebernehmen und eine neue Karte wuerfeln."""
        m = self.menu
        if m.kartenart() == "abschnitt":
            gr = m.groesse()
            self.size = gr if gr != "eigene" else m.eigene_masse()
            self.masse = None
        else:
            self.size = None
            gr = m.groesse()
            self.masse = gr if isinstance(gr, tuple) else None
        self.safe = m.safe_name
        self.safe_masse = m.safe_size if m.safe_name == "eigene" else None
        self.ecke = m.ecke
        self.hud_name, self.theme_name = m.hud, m.schema
        if m.mode is not None:
            self.mode = m.mode
        elif m.gruppe != "alle":
            # Gruppe ohne feste Art: eine daraus ziehen, sonst waere die
            # Einstellung wirkungslos.
            self.mode = random.choice(m.arten())
        else:
            self.mode = None
        # Eingegebener Seed schlaegt Wuerfeln. Steht dort nichts, wird
        # gewuerfelt - das ist der uebliche Fall.
        self.load(m.seed if m.seed is not None
                  else random.randrange(1, 10 ** 9))

    def flash(self, msg):
        self.status = msg
        self.status_t = 3.5

    def export(self):
        """Was gerade zu sehen ist, rausschreiben.

        PNG und JSON in `export/`, dazu die Tiled-Fassung in
        `tiled_export/` - inklusive Tileset mit Kollision. Damit landet
        ein Abschnitt, der einem im Viewer gefaellt, mit einem Tastendruck
        dort, wo man ihn braucht.
        """
        bp = self.world.blueprint
        if bp is None:
            self.flash("Nichts zu exportieren: handgesetztes Layout")
            return
        ziel = self.export_dir
        os.makedirs(ziel, exist_ok=True)
        if self.size is None and self.masse is None:
            name = "map_%d" % bp.seed
        elif self.size is None:
            name = "karte_%dx%d_%s_%d" % (bp.w, bp.h, bp.mode, bp.seed)
        else:
            # Bei eigenen Massen ist self.size ein Zahlenpaar - dessen
            # Schreibweise gehoert nicht in einen Dateinamen.
            kennung = (self.size if isinstance(self.size, str)
                       else "%dx%d" % (bp.w, bp.h))
            name = "abschnitt_%s_%s_%d" % (kennung, bp.mode, bp.seed)
        base = os.path.join(ziel, name)
        surf = pygame.Surface((self.world.w * TILE,
                               self.world.h * TILE)).convert()
        surf.fill(C_BG)
        self.world.draw(surf, (0, 0))
        pygame.image.save(surf, base + ".png")
        bp.dump_json(base + ".json")

        try:
            n_ts = self._export_tiled(bp, name)
        except Exception as err:
            self.flash("%s.png + .json - Tiled-Export scheiterte: %s"
                       % (name, err))
            return
        self.flash("%s + %d Tilesets -> %s"
                   % (name, n_ts, paths.kuerzen(ziel, 30)))

    def _export_tiled(self, bp, name):
        """Dieselbe Karte als .tmx neben das Tileset legen."""
        from tools import export_tiled as T
        # Die .tmx braucht ihre Tilesets neben sich - deshalb ein eigener
        # Unterordner statt alles auf einen Haufen.
        out = os.path.join(self.export_dir, "tiled")
        os.makedirs(out, exist_ok=True)
        # Bei jedem Export das ganze Paket danebenlegen. Das kostet 100 KB
        # und erspart die Frage, welche Grafik denn nun fehlt.
        cols, rows = T.atlas_png(os.path.join(out, T.PNG_NAME))
        tilesets = T.schreibe_tilesets(out, cols, rows)
        T.write_tmx(os.path.join(out, name + ".tmx"), bp, cols, tilesets)
        return len(tilesets)

    # ------------------------------------------------------------- Anzeige
    def _set_mode(self):
        """Fenstermodus setzen. Gibt zurueck, ob es geklappt hat.

        Frueher standen hier zwei Versuche und beide mit `SCALED`. Wenn
        SDL dafuer keinen Renderer aufbauen kann - was auf manchen
        Treibern genau beim Wechsel ins Vollbild passiert - flog die
        Ausnahme bis nach oben durch und der Viewer war weg. Ein
        Anzeigemodus, den die Grafikkarte nicht mag, darf aber kein Grund
        sein, das Programm zu beenden.

        Deshalb eine Leiter: erst der schoene Modus, dann ohne vsync,
        dann ohne SCALED, zuletzt ein schlichtes Fenster. Ohne SCALED
        skaliert `draw_scene()` ohnehin selbst auf die Fenstergroesse.
        """
        size = (VIEW_W * self.scale, VIEW_H * self.scale)
        if self.fullscreen:
            versuche = (
                (pygame.SCALED | pygame.FULLSCREEN, size, True),
                (pygame.SCALED | pygame.FULLSCREEN, size, False),
                (pygame.FULLSCREEN, (0, 0), False),
                (pygame.NOFRAME, (0, 0), False),
            )
        else:
            versuche = (
                (pygame.SCALED | pygame.RESIZABLE, size, True),
                (pygame.SCALED | pygame.RESIZABLE, size, False),
                (pygame.RESIZABLE, size, False),
                (0, size, False),
            )
        for flags, sz, vsync in versuche:
            try:
                if vsync:
                    self.screen = pygame.display.set_mode(sz, flags, vsync=1)
                else:
                    self.screen = pygame.display.set_mode(sz, flags)
            except Exception:
                # Absichtlich jede Ausnahme: welche SDL beim Aufbau eines
                # Fensters wirft, haengt am Treiber, und keine davon ist
                # ein Grund, den Viewer zu beenden.
                continue
            self._scaled = bool(flags & pygame.SCALED)
            self._sync_surfaces()
            return True
        return False

    def _fit_camera(self):
        """Kamerabegrenzung und Uebersichtsflaeche an die Karte anpassen.

        Ein Abschnitt ist kleiner als das Fenster - dann darf die Kamera
        gar nicht wandern, sonst schiebt man die Karte aus dem Bild.
        """
        w, h = self.world.w * TILE, self.world.h * TILE
        self.cam_max = (max(0, w - VIEW_W), max(0, h - VIEW_H))
        self.cam[0] = min(self.cam[0], self.cam_max[0])
        self.cam[1] = min(self.cam[1], self.cam_max[1])
        if w <= VIEW_W:
            self.cam[0] = -(VIEW_W - w) // 2      # kleine Karte mittig
        if h <= VIEW_H:
            self.cam[1] = -(VIEW_H - h) // 2
        self.overview_surf = pygame.Surface((w, h)).convert()

    def _sync_surfaces(self):
        """Zeichenflaechen an das aktuelle Fenster angleichen.

        `convert()` bindet eine Flaeche an das Pixelformat, das beim
        Erzeugen galt. Nach einem Moduswechsel kann das Fenster ein
        anderes haben - und `transform.scale` mit Zielflaeche verlangt
        gleiches Format. Ohne das faellt der Unterschied erst beim
        naechsten Bild auf, und dann als Absturz.
        """
        w = self.world.w * TILE if hasattr(self, "world") else MAP_W * TILE
        h = self.world.h * TILE if hasattr(self, "world") else MAP_H * TILE
        try:
            self.view = pygame.Surface((VIEW_W, VIEW_H)).convert()
            self.overview_surf = pygame.Surface((w, h)).convert()
        except Exception:
            self.view = pygame.Surface((VIEW_W, VIEW_H))
            self.overview_surf = pygame.Surface((w, h))

    def toggle_fullscreen(self):
        """Vollbild an/aus.

        Solange `SCALED` aktiv ist, geht das ueber
        `pygame.display.toggle_fullscreen()`. Das ist bei SCALED der
        vorgesehene Weg und laesst das Fenster stehen. Ein zweites
        `set_mode()` baut es dagegen komplett neu auf - und genau daran
        scheitert SDL auf manchen Treibern, mit einem Renderer, den es
        nicht mehr anlegen kann.

        Erst wenn das nicht geht, kommt der Neuaufbau ueber die Leiter in
        `_set_mode()`. Und wenn auch der scheitert, laeuft das bisherige
        Fenster weiter - F11 darf den Viewer nicht beenden.
        """
        if self._scaled:
            try:
                pygame.display.toggle_fullscreen()
                self.fullscreen = not self.fullscreen
                self._sync_surfaces()
                return
            except Exception:
                pass

        self.fullscreen = not self.fullscreen
        if self._set_mode():
            return
        self.fullscreen = not self.fullscreen
        if self._set_mode():
            self.flash("Vollbild geht auf diesem Rechner nicht")
        else:
            self.flash("Anzeigemodus liess sich nicht wechseln")

    def font(self, size, bold=False):
        key = (size, bold)
        if not hasattr(self, "_fonts"):
            self._fonts = {}
        f = self._fonts.get(key)
        if f is None:
            f = pygame.font.SysFont("consolas,couriernew,monospace", size, bold=bold)
            self._fonts[key] = f
        return f

    def text(self, s, pos, size, color, bold=False, anchor="topleft"):
        f = self.font(size, bold)
        img = f.render(s, True, color)
        sh = f.render(s, True, (0, 0, 0))
        r = img.get_rect(**{anchor: pos})
        self.screen.blit(sh, (r.x + 1, r.y + 1))
        self.screen.blit(img, r)
        return r

    # ------------------------------------------------------------- Eingabe
    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN and self.menu is not None:
                self._menu_click(ev.pos)
            elif ev.type == pygame.KEYDOWN:
                # Solange das Menue offen ist, gehoeren die Tasten ihm -
                # sonst waelzt Links/Rechts gleichzeitig die Karte.
                if self.menu is not None and self._menu_key(ev):
                    continue
                if ev.key == pygame.K_ESCAPE:
                    self.running = False
                elif ev.key == pygame.K_F11:
                    self.toggle_fullscreen()
                elif ev.key == pygame.K_m:
                    self.overview = not self.overview
                elif ev.key == pygame.K_h:
                    self.show_help = not self.show_help
                elif ev.key == pygame.K_g:
                    self.show_grid = not self.show_grid
                elif ev.key == pygame.K_t:
                    self.world.door_open = 0.0 if self.world.door_open > 0.5 else 1.0
                elif ev.key == pygame.K_r:
                    self.load(random.randrange(1, 10 ** 9))
                elif ev.key in (pygame.K_n, pygame.K_p):
                    # Nachbarseeds durchblaettern - so findet man eine
                    # Karte wieder, an der man gerade vorbeigelaufen ist.
                    step = 1 if ev.key == pygame.K_n else -1
                    base = self.seed if self.seed is not None else 1
                    self.load(max(1, base + step))
                elif ev.key == pygame.K_l:
                    self.load(None if self.seed is not None else 1)
                elif ev.key == pygame.K_k:
                    self.show_spawns = not self.show_spawns
                elif ev.key == pygame.K_e:
                    self.export()
                elif ev.key in (pygame.K_F1, pygame.K_F2):
                    self.menu = Menu(
                        self.size if isinstance(self.size, str)
                        else ("eigene" if self.size or self.masse else None),
                        "alle" if self.mode is None
                        else mapgen.MODES[self.mode]["gruppe"],
                        self.mode, self.seed, self.export_dir,
                        self.safe, self.ecke,
                        self.masse or (self.size if isinstance(self.size, tuple)
                                       else None),
                        self.safe_masse, self.hud_name, self.theme_name)
                elif ev.key in _GRUPPENTASTEN:
                    self.jump_group(_GRUPPENTASTEN[ev.key])
                elif ev.key == pygame.K_TAB:
                    step = -1 if (ev.mod & pygame.KMOD_SHIFT) else 1
                    self.cycle_mode(step)
                elif ev.key == pygame.K_c:
                    # Zurueck auf "je Seed gewuerfelt".
                    self.mode = None
                    self.load(self.seed if self.seed is not None
                              else random.randrange(1, 10 ** 9))

    def pan(self, dt):
        keys = pygame.key.get_pressed()
        dx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        dy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        if not (dx or dy):
            return
        sp = PAN_FAST if (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) else PAN_SPEED
        if dx and dy:
            sp *= 0.7071
        self.cam[0] += dx * sp * dt
        self.cam[1] += dy * sp * dt
        self.cam[0] = max(0, min(self.cam_max[0], self.cam[0]))
        self.cam[1] = max(0, min(self.cam_max[1], self.cam[1]))

    # ------------------------------------------------------------ Zeichnen
    def box(self, rect, alpha=178):
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill(self.T["kasten"] + (alpha,))
        self.screen.blit(bg, rect.topleft)
        pygame.draw.rect(self.screen, self.T["rand"], rect,
                         max(1, int(self.scale) // 2))

    def draw_grid(self, surf, cam):
        """Tileraster, jede 8. Linie kraeftiger zur Orientierung."""
        thin = (120, 200, 255, 62)
        thick = (255, 210, 110, 130)
        overlay = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
        t0 = int(cam[0]) // TILE
        x0 = -(int(cam[0]) % TILE)
        for i, x in enumerate(range(x0, VIEW_W, TILE)):
            pygame.draw.line(overlay, thick if (t0 + i) % 8 == 0 else thin,
                             (x, 0), (x, VIEW_H))
        t0 = int(cam[1]) // TILE
        y0 = -(int(cam[1]) % TILE)
        for i, y in enumerate(range(y0, VIEW_H, TILE)):
            pygame.draw.line(overlay, thick if (t0 + i) % 8 == 0 else thin,
                             (0, y), (VIEW_W, y))
        surf.blit(overlay, (0, 0))

    def draw_safe_outline(self, surf, cam):
        if not self.world.has_safe:
            return
        r = self.world.safe_rect.union(self.world.gate_rect)
        rr = pygame.Rect(r.x - cam[0], r.y - cam[1], r.w, r.h)
        tint = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        tint.fill((46, 122, 156, 46))
        surf.blit(tint, rr.topleft)
        pygame.draw.rect(surf, self.T["aktiv"], rr, 1)

    def draw_spawns(self, surf, cam, size=3):
        """Wellen-Spawnpunkte als Ring - die Karte sagt, wo es losgeht."""
        for (tx, ty) in self.world.spawns:
            cx = tx * TILE + TILE // 2 - cam[0]
            cy = ty * TILE + TILE // 2 - cam[1]
            if not (-8 <= cx <= surf.get_width() + 8
                    and -8 <= cy <= surf.get_height() + 8):
                continue
            pygame.draw.circle(surf, self.T["spawn"], (int(cx), int(cy)), size, 1)
            pygame.draw.circle(surf, self.T["spawn"], (int(cx), int(cy)), max(1, size - 2))

    def draw_scene(self):
        cam = (int(self.cam[0]), int(self.cam[1]))
        self.view.fill(C_BG)
        self.world.draw(self.view, cam)
        self.draw_safe_outline(self.view, cam)
        if self.show_spawns:
            self.draw_spawns(self.view, cam)
        if self.show_grid:
            self.draw_grid(self.view, cam)
        pygame.transform.scale(self.view, self.screen.get_size(), self.screen)

    def draw_overview(self):
        self.overview_surf.fill(C_BG)
        self.world.draw(self.overview_surf, (0, 0))
        if self.world.has_safe:
            r = self.world.safe_rect.union(self.world.gate_rect)
            tint = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            tint.fill((46, 122, 156, 46))
            self.overview_surf.blit(tint, r.topleft)
            pygame.draw.rect(self.overview_surf, self.T["aktiv"], r, 1)
        if self.show_spawns:
            self.draw_spawns(self.overview_surf, (0, 0), size=4)

        W, H = self.screen.get_size()
        mw, mh = self.overview_surf.get_size()
        f = min((W - 40) / mw, (H - 60) / mh)
        f = max(1.0, int(f)) if f >= 1 else f
        dw, dh = int(mw * f), int(mh * f)
        self.screen.fill((8, 8, 13))
        self.screen.blit(pygame.transform.scale(self.overview_surf, (dw, dh)),
                         ((W - dw) // 2, (H - dh) // 2))
        # Ausschnitt der Nahansicht markieren
        vx = (W - dw) // 2 + int(self.cam[0] * f)
        vy = (H - dh) // 2 + int(self.cam[1] * f)
        pygame.draw.rect(self.screen, self.T["akzent"],
                         (vx, vy, int(VIEW_W * f), int(VIEW_H * f)), max(1, int(f)))

    def draw_menu(self):
        """Das Auswahlmenue. Drei Zeilen, mittig ueber der Karte."""
        S = self.scale
        W, H = self.screen.get_size()
        zeilen = self.menu.zeilen()
        hinweise = self.menu.hinweise()

        # Spaltenbreite messen statt festlegen. Vorher stand hier eine
        # feste Zahl, und "Startraum-Ecke" lief in seinen Wert hinein.
        gross = self.font(int(8 * S), True)
        klein = self.font(int(7 * S), True)
        kw = max(gross.size("> " + n)[0] for _, n, _ in zeilen) + 16 * S
        kw = max(kw, max(klein.size(k)[0] for k, _ in hinweise) + 12 * S)
        vw = max(gross.size(w)[0] for _, _, w in zeilen)
        vw = max(vw, max(self.font(int(7 * S)).size(w)[0]
                         for _, w in hinweise) + 8 * S)
        bw = min(W - 16 * S, kw + vw + 22 * S)
        bh = (len(zeilen) * 13 + len(hinweise) * 9 + 30) * S
        r = pygame.Rect(0, 0, bw, bh)
        r.center = (W // 2, H // 2)
        r.clamp_ip(pygame.Rect(0, 0, W, H))
        self.box(r, alpha=232)

        self.text("AUSWAHL", (r.centerx, r.y + 8 * S), int(10 * S), self.T["akzent"],
                  bold=True, anchor="midtop")
        y = r.y + 24 * S
        self._menu_rects = []
        self._menu_text_x = r.x + kw + 3 * S
        for i, (key, name, wert) in enumerate(zeilen):
            aktiv = i == self.menu.row
            bar = pygame.Rect(r.x + 5 * S, y - 2 * S, bw - 10 * S, 12 * S)
            self._menu_rects.append(bar)
            if aktiv:
                pygame.draw.rect(self.screen, self.T["balken"], bar)
            self.text(("> " if aktiv else "  ") + name, (r.x + 10 * S, y),
                      int(8 * S), self.T["aktiv"] if aktiv else self.T["dim"], bold=aktiv)
            feld = self.menu.feld(key)
            if feld is not None:
                self._draw_feld(feld, key, r.x + kw, y, vw, S, aktiv, wert)
            else:
                self.text(wert, (r.x + kw, y), int(8 * S),
                          self.T["text"] if aktiv else self.T["dim"], bold=aktiv)
            y += 13 * S

        y += 6 * S
        for k, was in hinweise:
            self.text(k, (r.x + kw - 6 * S, y), int(7 * S), self.T["akzent"],
                      bold=True, anchor="topright")
            self.text(was, (r.x + kw, y), int(7 * S), self.T["dim"])
            y += 9 * S

    def _draw_feld(self, f, key, x, y, breite, S, aktiv, wert=""):
        """Ein Textfeld: Rahmen, Inhalt, blinkende Schreibmarke.

        Der Kasten ist schmal - eine Zahl braucht nicht die volle Breite -
        und was rechts daneben noch in der Zeile stand (etwa "-> 68 x 46")
        wird daneben gesetzt, nicht darueber. Genau da haben sich die
        Texte vorher ueberlagert.
        """
        eng = key != "seed"
        kb = (34 * S) if eng else min(breite, 74 * S)
        kasten = pygame.Rect(x, y - 2 * S, kb, 12 * S)
        pygame.draw.rect(self.screen, self.T["kasten"], kasten)
        pygame.draw.rect(self.screen, self.T["aktiv"] if aktiv else self.T["rand"],
                         kasten, max(1, S // 2))

        tx = x + 3 * S
        if not f.text:
            self.text("(zufaellig)" if key == "seed" else "-",
                      (tx, y), int(8 * S), self.T["dim"])
        else:
            self.text(f.text, (tx, y), int(8 * S), self.T["text"], bold=aktiv)

        # Rest der Zeile hinter dem Kasten, nicht darauf.
        nach = wert.split("->", 1)
        if len(nach) == 2:
            self.text("-> " + nach[1].strip(), (x + kb + 6 * S, y),
                      int(7 * S), self.T["dim"])

        if not aktiv:
            return
        # Blinken, damit das Feld als Eingabe zu erkennen ist.
        if (pygame.time.get_ticks() // 500) % 2 == 0:
            schrift = self.font(int(8 * S), True)
            vor = f.parts()[0]
            cx = tx + schrift.size(vor)[0]
            pygame.draw.line(self.screen, self.T["text"],
                             (cx, y + 1 * S), (cx, y + 10 * S), max(1, S // 2))

    def draw_hud(self):
        S = self.hs
        W, H = self.screen.get_size()
        pad = 8 * S
        mode = "GESAMTANSICHT" if self.overview else "NAHANSICHT"
        tx = int(self.cam[0] + VIEW_W / 2) // TILE
        ty = int(self.cam[1] + VIEW_H / 2) // TILE

        bp = self.world.blueprint
        zeilen = [("ARENA - MAP VIEWER", int(10 * S), self.T["akzent"], True),
                  (mode, int(8 * S), self.T["aktiv"], True),
                  ("Mitte  Tile %d,%d   Karte %dx%d"
                   % (tx, ty, self.world.w, self.world.h),
                   int(7 * S), self.T["dim"], False)]
        if bp is None:
            zeilen.append(("Layout: handgesetzt", int(7 * S),
                           self.T["dim"], False))
        else:
            # Zwei Zeilen statt einer langen. Vorher lief die Angabe weit
            # ueber den Kasten hinaus und ins Kartenbild hinein.
            zeilen.append(("%s / %s   Seed %d" % (bp.group, bp.mode, bp.seed),
                           int(7 * S), self.T["akzent"], False))
            rest = "%d%% offen   %d Spawns" % (round(bp.open_ratio * 100),
                                               len(bp.spawns))
            if bp.has_safe:
                sx0, sy0, sx1, sy1 = bp.safe
                rest += "   Start %dx%d %s" % (sx1 - sx0 + 1, sy1 - sy0 + 1,
                                               bp.safe_pos)
            zeilen.append((rest, int(7 * S), self.T["dim"], False))

        breite = max(self.font(g, b).size(t)[0] for t, g, _c, b in zeilen)
        hoehe = sum(int(g * 1.35) + 2 * S for t, g, _c, b in zeilen)
        self.box(pygame.Rect(pad - 4 * S, pad - 4 * S,
                             breite + 10 * S, hoehe + 6 * S))
        y = pad
        for t, g, c, b in zeilen:
            self.text(t, (pad, y), g, c, bold=b)
            y += int(g * 1.35) + 2 * S

        if self.status_t > 0:
            self.text(self.status, (W // 2, H - pad - 4 * S), int(8 * S),
                      self.T["text"], bold=True, anchor="midbottom")

        if self.menu is not None:
            self.draw_menu()
            return

        if not self.show_help:
            r = pygame.Rect(0, 0, 44 * S, 13 * S)
            r.topright = (W - pad + 4 * S, pad - 3 * S)
            self.box(r)
            self.text("[H] Hilfe", r.center, int(7 * S), self.T["dim"],
                      anchor="center")
            return
        lines = [
            ("F1", "Auswahlmenue"),
            ("1 2 3 4", "Gruppe waehlen"),
            ("TAB", "naechste Kartenart"),
            ("S-TAB", "vorige Kartenart"),
            ("C", "Art wieder wuerfeln"),
            ("R", "neue Karte wuerfeln"),
            ("N / P", "Seed vor / zurueck"),
            ("WASD", "Karte bewegen"),
            ("SHIFT", "schneller bewegen"),
            ("L", "handgesetzt <-> generiert"),
            ("K", "Spawnpunkte an/aus"),
            ("E", "exportieren"),
            ("M", "Gesamtansicht an/aus"),
            ("G", "Tileraster an/aus"),
            ("T", "Tor oeffnen/schliessen"),
            ("F11", "Vollbild"),
            ("H", "Hilfe ausblenden"),
            ("ESC", "Beenden"),
        ]
        # Auch hier gemessen statt geraten - bei grosser Schrift lief die
        # Tastenspalte sonst in die Beschreibung.
        fett = self.font(int(7 * S), True)
        mager = self.font(int(7 * S))
        kw = max(fett.size(k)[0] for k, _ in lines) + 6 * S
        vw = max(mager.size(t)[0] for _, t in lines)
        r = pygame.Rect(0, 0, kw + vw + 14 * S, len(lines) * 10 * S + 8 * S)
        r.topright = (W - pad + 4 * S, pad - 3 * S)
        r.clamp_ip(pygame.Rect(0, 0, W, H))
        self.box(r)
        y = r.y + 4 * S
        for k, t in lines:
            self.text(k, (r.x + kw, y), int(7 * S), self.T["akzent"],
                      bold=True, anchor="topright")
            self.text(t, (r.x + kw + 5 * S, y), int(7 * S), self.T["text"])
            y += 10 * S

    def run(self):
        while self.running:
            dt = min(0.05, self.clock.tick(FPS) / 1000.0)
            self.handle_events()
            # Solange das Menue offen ist, gehoeren die Pfeiltasten ihm.
            # Sonst waelzt sich die Karte unter dem Menue weg, waehrend
            # man die Schreibmarke bewegt.
            if self.menu is None:
                self.pan(dt)
            self.world.update(dt)
            if self.status_t > 0:
                self.status_t -= dt
            # Letzte Sicherung: bricht die Anzeige unter uns weg - etwa
            # weil ein Moduswechsel den Renderer zerlegt hat -, wird
            # einmal neu aufgebaut. Klappt das nicht, endet der Viewer mit
            # einem Satz statt mit einem Stapelabzug.
            try:
                if self.overview:
                    self.draw_overview()
                else:
                    self.draw_scene()
                self.draw_hud()
                pygame.display.flip()
            except pygame.error as err:
                if self._set_mode():
                    self.flash("Anzeige neu aufgebaut")
                else:
                    print("Anzeige verloren: %s" % err)
                    self.running = False
        pygame.quit()
