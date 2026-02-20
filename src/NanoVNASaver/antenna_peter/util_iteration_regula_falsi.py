"""
>>> iter = iteration(ySoll=1.0, yToleranz=0.01, xMin=4000, xMax=60000, iMax=20)
>>> x = iter.startX()
>>> x
32000
>>> iter.weiter()
True
>>> x = int(iter.naechstesX(x, 2.063439))
>>> x
22760
>>> x = int(iter.naechstesX(x, 1.454376))
>>> x
16569
>>> x = int(iter.naechstesX(x, 1.050694))
>>> x
12421
>>> x = int(iter.naechstesX(x, 0.781948))
>>> x
15786
>>> x = int(iter.naechstesX(x, 0.970209))
>>> x
16075
>>> x = int(iter.naechstesX(x, 0.970241))
>>> x
16257
>>> x = int(iter.naechstesX(x, 0.918450))
>>> x
16449
>>> x = int(iter.naechstesX(x, 0.928235))
>>> x
16519
>>> x = int(iter.naechstesX(x, 0.931395))
>>> x
16547
>>> x = int(iter.naechstesX(x, 0.932692))
>>> x
16559
>>> x = int(iter.naechstesX(x, 0.933392))
>>> x
16564
>>> x = int(iter.naechstesX(x, 0.933726))
>>> x
16566
>>> x = int(iter.naechstesX(x, 0.933919))
>>> x
16567
>>> x = int(iter.naechstesX(x, 0.933972))
>>> x
16568
>>> x = int(iter.naechstesX(x, 0.934087))
>>> x
16568
>>> x = int(iter.naechstesX(x, 0.934094))
>>> x
16568
>>> x = int(iter.naechstesX(x, 0.934115))
>>> x
16568
>>> x = int(iter.naechstesX(x, 0.934184))
>>> x
16568
>>> x = int(iter.naechstesX(x, 0.934193))
>>> x
16568

"""

# import random


class iteration:
    """Implementiert das Finden eines bestimmten Wertes"""

    def __init__(self, ySoll, yToleranz, xMin, xMax, iMax, iPlus=0, k=0.33):
        self.ySoll = ySoll
        self.yToleranz = yToleranz
        self.xMin = xMin
        self.xMax = xMax
        self.k = k
        self.i = 1
        self.iMax = iMax
        self.iPlus = abs(
            iPlus
        )  # Anzahl zusaetzliche Iterationen nach erreichen von yToleranz
        self.yMin = None
        self.yMax = None
        self.bOk = False
        self.listLogTable = []
        self.strFehler = "Noch keine Iteration"
        self.xLast = None
        self.xLastLast = None

    def write_to_logger(self, objLogger, strClass, strTitle):
        if not self.bOk:
            strTitle = "FEHLER: %s (%s)" % (strTitle, self.strFehler)
        else:
            strTitle = "OK: %s" % strTitle
        objLogger.table(
            strClass,
            strTitle,
            (("Abgleichschritt"), ("X"), ("Y"), ("YSoll")),
            self.listLogTable,
        )

    def write_to_print(self):
        print(self.listLogTable, self.strFehler)

    def startX(self):
        return (self.xMax + self.xMin) / 2

    def weiter(self):
        """return False, falls Toleranz erreicht oder bei Fehler"""
        self.i = self.i + 1

        if self.bOk:
            # Wir durchlaufen die iPlus-Iterationen, unabhaengig vom Ergebnis
            # print 'self.iPlus %d' % self.iPlus
            if self.iPlus > 0 and self.xLast != self.xLastLast:
                self.iPlus = self.iPlus - 1
                return True
            return False
        if self.i > self.iMax:
            self.strFehler = "%d Iteration ueberschritten" % self.iMax
            return False
        x, y = self.bestes()
        if x is None:
            return True
        if abs(y - self.ySoll) <= self.yToleranz:
            self.bOk = True
            self.strFehler = "ok"
            if self.iPlus > 0:
                # Wir machen noch ein paar Extra-Loops
                if self.xLastLast and (self.xLastLast == self.xLast):
                    # Der neue Schaetzwert ist gleich wie der letzte
                    # Schaetzwert: Weitere Messungen sind sinnlos.
                    return False
                return True
            return False
        # if int(self.xMax) == int(self.xMin) and self.xMin != None:
        #   self.strFehler = "xMax == xMin, %d" % self.xMax
        #   return False
        return True

    def bestes(self):
        if (self.yMin is not None) and (self.yMax is None):
            return self.xMin, self.yMin
        if (self.yMax is not None) and (self.yMin is None):
            return self.xMax, self.yMax
        if (self.yMin is None) and (self.yMax is None):
            return None, None
        minAbweichung = self.ySoll - self.yMin
        maxAbweichung = self.yMax - self.ySoll
        if maxAbweichung > minAbweichung:
            return self.xMin, self.yMin
        return self.xMax, self.yMax

    def naechstesX(self, x, y, objLogger=None):
        x_tmp = x
        x = self.__naechstesX(x, y)
        self.listLogTable.append(
            (
                ("INFO", str(self.i - 1)),
                ("INFO", "%7.1f" % x_tmp),
                ("INFO", "%8.6f" % y),
                ("INFO", "%8.6f +/-%4.4f" % (self.ySoll, self.yToleranz)),
            )
        )
        self.xLastLast = self.xLast
        self.xLast = x
        return x

    def __naechstesX(self, x, y):
        """Bestimmt den naechsten Wert gemaess Rugula Falsi oder Karl Otto Rumenigge"""
        if self.ySoll > y:
            self.xMin, self.yMin = x, y
            if self.yMax is None:
                # Karl Otto Rumenigge
                return (self.xMax - x) * self.k + xiteraton
        else:
            self.xMax, self.yMax = x, y
            if self.yMin is None:
                # Karl Otto Rumenigge
                return (self.xMin - x) * self.k + x
        # Regula Falsi
        return self.xMin + (self.ySoll - self.yMin) * (
            self.xMax - self.xMin
        ) / (self.yMax - self.yMin)
        # return random.randrange(self.xMin, self.xMax)# An der Grenze der Auloesung der DAC's: Zufallswerte

    def resultat(self):
        return self.bOk, self.strFehler


def test():
    import doctest  # noqa: PLC0415
    import iteration  # noqa: PLC0415

    return doctest.testmod(iteration)


if __name__ == "__main__":
    test()
