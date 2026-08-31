"""Ein richtiges Textfeld: Cursor, Korrigieren, Einfuegen.

Vorher wurden Ziffern nur hinten angehaengt. Das reicht, solange man sich
nicht vertippt - und genau dann eben nicht: eine Ziffer in der Mitte war
nur ueber komplettes Loeschen zu erreichen, und einen Seed aus der
Zwischenablage einzusetzen ging gar nicht.

Bewusst ohne Markierung mit der Maus. Ein Seed ist eine kurze Zahl; alles
darueber hinaus waere Aufwand fuer einen Fall, den es hier nicht gibt.
"""


class TextField:
    """Text mit Schreibmarke. Zeichnen macht der Aufrufer."""

    def __init__(self, text="", max_len=9, digits_only=True):
        self.max_len = max_len
        self.digits_only = digits_only
        self.text = ""
        self.caret = 0
        self.set_text(text)

    # ------------------------------------------------------------ Inhalt
    def set_text(self, text):
        text = "".join(c for c in str(text)
                       if not self.digits_only or c.isdigit())
        self.text = text[:self.max_len]
        self.caret = len(self.text)

    def clear(self):
        self.text = ""
        self.caret = 0

    def insert(self, zeichen):
        for c in zeichen:
            if self.digits_only and not c.isdigit():
                continue
            if len(self.text) >= self.max_len:
                break
            self.text = self.text[:self.caret] + c + self.text[self.caret:]
            self.caret += 1

    def backspace(self):
        if self.caret > 0:
            self.text = self.text[:self.caret - 1] + self.text[self.caret:]
            self.caret -= 1

    def delete(self):
        if self.caret < len(self.text):
            self.text = self.text[:self.caret] + self.text[self.caret + 1:]

    # ------------------------------------------------------------- Marke
    def left(self):
        self.caret = max(0, self.caret - 1)

    def right(self):
        self.caret = min(len(self.text), self.caret + 1)

    def home(self):
        self.caret = 0

    def end(self):
        self.caret = len(self.text)

    def caret_from_x(self, x, breite_von):
        """Schreibmarke dorthin setzen, wo geklickt wurde.

        `breite_von(n)` liefert die Pixelbreite der ersten n Zeichen -
        damit muss dieses Modul nichts ueber Schriften wissen.
        """
        best, best_d = 0, None
        for i in range(len(self.text) + 1):
            d = abs(breite_von(i) - x)
            if best_d is None or d < best_d:
                best, best_d = i, d
        self.caret = best

    # -------------------------------------------------------- Zwischenab.
    def paste(self):
        """Aus der Zwischenablage einfuegen.

        Ueber tkinter, das ohnehin fuer den Ordnerdialog mitgepackt wird.
        Fehlt es oder ist die Ablage leer, passiert nichts - ein
        misslungenes Einfuegen darf nicht mehr sein als ein Nichtereignis.
        """
        try:
            import tkinter
            wurzel = tkinter.Tk()
            wurzel.withdraw()
            try:
                inhalt = wurzel.clipboard_get()
            finally:
                wurzel.destroy()
        except Exception:
            return False
        vorher = self.text
        self.insert(inhalt.strip())
        return self.text != vorher

    # ------------------------------------------------------------- Werte
    def as_int(self):
        return int(self.text) if self.text else None

    def parts(self):
        """Text vor und nach der Schreibmarke - fuers Zeichnen."""
        return self.text[:self.caret], self.text[self.caret:]
