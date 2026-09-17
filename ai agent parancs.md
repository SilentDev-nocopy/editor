# Resiris IDE – AI Agent fejlesztési specifikáció

## 1. Cél

Készíts egy egyszerű, önálló Resiris IDE-t.

A cél nem egy csicsás, teljes értékű általános IDE létrehozása, hanem egy kifejezetten a **Resiris programozási nyelvhez** készült kis fejlesztőkörnyezet.

Az IDE elsődleges céljai:

* `.resy` fájlok szerkesztése
* Resiris syntax highlighting
* Resiris parser használata
* hibák felismerése
* sárga/piros diagnosztikák
* autocomplete / autofill
* modulok felismerése
* hiányzó `include` automatikus javítása
* egyszerű Resiris program futtatás
* egyszerű output / hibakimenet

Nem cél:

* komplex fájlkezelő rendszer
* git kliens
* debugger
* terminál-emulátor
* plugin marketplace
* rengeteg beállítás
* látványos animációk
* általános célú IDE
* VS Code funkcionalitásának lemásolása

Az IDE legyen kicsi, gyors és könnyen továbbfejleszthető.

---

# 2. FONTOS: A MEGLÉVŐ RESIRIS PROJEKT AZ IGAZSÁG FORRÁSA

A fejlesztés előtt vizsgáld meg a teljes meglévő Resiris projektet.

A projektben található aktuális fájlok és implementációk elsőbbséget élveznek minden általános tudással vagy feltételezéssel szemben.

NE találj ki új Resiris-szabályokat.

NE változtasd meg a Resiris nyelvet azért, hogy egyszerűbb legyen az IDE implementációja.

Ha valami nincs definiálva a projektben, azt ne implementáld saját elképzelés alapján.

A Resiris aktuális szintaxisát, kulcsszavait, típusait, modulrendszerét és egyéb működését a meglévő projektből kell meghatározni.

Különösen fontos:

* `START()`
* `PROCESS()`
* `fn`
* `v`
* `c`
* `include`
* aktuális típusok
* aktuális modulrendszer
* aktuális függvények
* aktuális hibák

A projektben található újabb specifikáció mindig fontosabb egy régi fájlnál.

---

# 3. Technológia

Javasolt architektúra:

## Frontend

TypeScript.

Egyszerű webes UI.

Használható például:

* HTML
* CSS
* TypeScript

Nem szükséges komplex frontend framework.

Ha framework használata ténylegesen segít, lehet használni, de ne legyen szükségtelenül nagy dependency.

## Desktop shell / backend

Rust + Tauri.

A Rust backend feladata lehet:

* fájlműveletek
* Resiris projekt kezelése
* Resiris parser / language core
* diagnosztika
* program futtatása
* process kezelés

A frontend kizárólag a UI-val és editor interactionnel foglalkozzon.

---

# 4. Nagyon fontos architekturális cél

A Resiris IDE ne tartalmazzon egy teljesen különálló, saját Resiris-értelmezést.

Ha a projektben már van:

* tokenizer
* parser
* AST
* interpreter

akkor az IDE ezeket használja, vagy ezekhez közös language-core réteget kell kialakítani.

A cél:

```text
                Resiris Language Core
                       │
          ┌────────────┼────────────┐
          │            │            │
         IDE          CLI       Interpreter
```

Ne legyen:

```text
Resiris parser
      +
külön IDE parser
```

mert idővel szét fognak csúszni.

---

# 5. IDE minimális UI

Az UI legyen egyszerű.

Például:

```text
┌──────────────────────────────────────────────┐
│ Resiris IDE                         Run  Stop │
├───────────┬──────────────────────────────────┤
│ Files     │ main.resy                        │
│           │                                  │
│ main.resy │ 1  include RSMath                │
│           │ 2                                  │
│ Modules   │ 3  v x = RSMath.sqrt(25)        │
│           │                                  │
│           │                                  │
│           │                                  │
├───────────┴──────────────────────────────────┤
│ Problems                                     │
│  ⚠ Missing include: RSMath                  │
├──────────────────────────────────────────────┤
│ Output                                       │
└──────────────────────────────────────────────┘
```

Nem kell:

* fancy sidebar
* animáció
* custom window decoration
* komplex theme engine
* drag-and-drop workspace
* extension marketplace

A funkcionalitás legyen fontosabb a kinézetnél.

---

# 6. Editor

Az IDE központi része egy Resiris kódszerkesztő.

Szükséges:

* `.resy` syntax highlighting
* sorok számozása
* tab / indentation kezelés
* keresés
* alapvető undo/redo
* cursor navigation
* file open/save
* modified state

A Resiris indentation-alapú nyelv.

Ezért az editor indentation kezelésének megbízhatónak kell lennie.

Ne formázza át automatikusan a felhasználó érvényes kódját saját stílusra.

---

# 7. Syntax highlighting

A highlightingot a tényleges Resiris nyelv alapján kell elkészíteni.

A már meglévő VS Code extension syntax grammarja felhasználható referenciának, de nem szabad vakon lemásolni.

Ellenőrizd a jelenlegi Resiris projektet.

A highlightingnak legalább külön kell kezelnie a tényleges:

* kommenteket
* stringeket
* számokat
* kulcsszavakat
* változókat / `v` deklarációkat
* konstansokat / `c` deklarációkat
* típusokat
* függvényeket
* modulokat
* operátorokat

A `START()` és `PROCESS()` aktuális Resiris konstrukciók, ezeket támogatni kell.

---

# 8. Autocomplete / Autofill

Ez az egyik legfontosabb funkció.

A felhasználó gépelés közben kapjon javaslatokat.

Például:

```text
inc
```

esetén:

```text
include
```

vagy megfelelő aktuális Resiris completion.

Ha:

```text
RSMath.
```

van a kódban, akkor az IDE az aktuálisan létező `RSMath` modulból kínáljon fel ténylegesen elérhető elemeket.

Például:

```text
RSMath.
       ├── sqrt
       ├── sin
       ├── cos
       └── ...
```

Csak olyan függvény jelenjen meg, amely ténylegesen létezik a projekt aktuális moduljában.

NE legyenek hardcoded, kitalált függvények.

---

# 9. Modul autocomplete

Az IDE ismerje fel a projektben található Resiris modulokat.

Ha a user ezt írja:

```text
include
```

akkor az IDE adjon modul-javaslatokat.

Például:

```text
include RSMath
include ResirisGameEngine
...
```

De csak a ténylegesen létező modulokból.

---

# 10. Hiányzó include felismerése

Ez kötelező funkció.

Ha a kód olyan modult használ, amelyhez szükséges az `include`, de az include hiányzik, az IDE adjon **warningot**.

Például:

```resy
v x = RSMath.sqrt(25)
```

ha az aktuális Resiris szabályok szerint ehhez szükséges:

```resy
include RSMath
```

akkor:

```text
RSMath
```

sárga warningot kap.

A diagnostic szövege legyen például:

```text
Missing include: RSMath
```

vagy a Resiris projekt terminológiájának megfelelő szöveg.

---

# 11. Quick Fix

A hiányzó include warninghoz legyen Quick Fix.

A user a warningon:

```text
💡 Missing include: RSMath
```

rendszerben kapjon egy:

```text
Javítás: include RSMath
```

lehetőséget.

A javítás automatikusan illessze be:

```resy
include RSMath
```

a megfelelő helyre.

Fontos:

* ne duplikálja az include-ot
* tartsa meg a meglévő kódot
* ne módosítsa feleslegesen az indentationt
* ne írja át az egész fájlt
* lehetőleg minimális text edit legyen

---

# 12. Nem létező modul

Ha például:

```resy
include FooBar
```

szerepel, de `FooBar` nem létezik az aktuális Resiris projektben, azt külön diagnostic jelezze.

Ez ne legyen összekeverve a hiányzó include problémával.

Két külön eset:

```text
Modul létezik + nincs include
→ WARNING + Quick Fix

Modul nem létezik
→ ERROR
```

---

# 13. Diagnostics

Az IDE folyamatosan ellenőrizze az aktuális fájlt.

Legalább:

### Syntax error

```text
ERROR
```

### Ismeretlen modul

```text
ERROR
```

### Hiányzó include

```text
WARNING
```

### Egyéb, a Resiris parser/runtime által ténylegesen definiált hibák

az aktuális Resiris hibakezelés szerint jelenjenek meg.

Ne találj ki új hibatípusokat csak az IDE kedvéért.

Ha a projektben például szerepel:

```text
UnknownVariableError
TypeError
ConstantAssignmentError
MissingValueError
SyntaxError
InvalidInputError
```

akkor ezekhez lehet IDE oldali megjelenítést készíteni.

---

# 14. Run

Legyen egy egyszerű:

```text
▶ Run
```

gomb.

Ez futtassa az aktuális Resiris programot a projekt tényleges interpreterével / runtime-jával.

NE legyen az IDE-ben egy külön fake interpreter.

A cél:

```text
Editor
   ↓
Resiris Language Core
   ↓
Resiris Interpreter
   ↓
Program
```

A program outputja jelenjen meg egy egyszerű Output panelben.

---

# 15. Stop

Legyen:

```text
■ Stop
```

gomb.

Ha a Resiris program külön processként fut, a Rust/Tauri backend tudja kezelni annak leállítását.

Ne implementáljunk még teljes debugger rendszert.

---

# 16. Projektkezelés

A projektkezelés legyen minimális.

Nem kell teljes filesystem explorer.

Elég például:

```text
Open Project
```

után a projekt `.resy` fájljai elérhetőek legyenek.

Lehet egy nagyon egyszerű lista:

```text
Files

main.resy
test.resy
Games/
```

Nem kell:

* file permissions UI
* advanced search index
* git integration
* rename refactoring
* file watcher rendszer, ha nem szükséges az első verzióhoz

---

# 17. Resiris modulok

Az IDE modulrendszerét ne hardcode-old.

A projekt aktuális modulstruktúráját kell használni.

Ha a projektben a moduloknak van definiált struktúrája, azt olvasd.

Az IDE számára legyen egy belső representation például:

```text
Module
 ├── name
 ├── functions
 ├── variables
 ├── constants
 └── other documented members
```

A pontos mezők a tényleges Resiris implementációból derüljenek ki.

---

# 18. Language Core

Ha szükséges, alakíts ki egy Rust crate-et:

```text
resiris-core
```

amelyben lehet:

```text
lexer
parser
ast
diagnostics
module resolution
symbol information
```

A későbbi IDE funkciók ezt használják.

Például:

```text
parse(source)
        ↓
AST
        ↓
diagnostics
        ↓
symbols
        ↓
autocomplete
```

Így az autocomplete nem egyszerű string matching lesz.

---

# 19. Symbol information

Az IDE tudjon legalább alapvető symbol table-t építeni.

Például:

```resy
v x int = 10
c PI float = 3.14

fn calculate():
    ...
```

Az IDE tudja:

```text
x → variable
PI → constant
calculate → function
```

Ez később lehetővé teszi:

* autocomplete
* hover
* symbol navigation
* diagnostics

implementálását.

Az első verzióban nem szükséges teljes refactoring engine.

---

# 20. Hover

Ha könnyen megvalósítható, legyen egyszerű hover.

Például:

```text
RSMath.sqrt
```

fölé állva:

```text
sqrt(...)
RSMath module function
```

A pontos információt a tényleges modul metadata alapján kell megjeleníteni.

Ha nincs dokumentáció, ne találj ki leírást.

---

# 21. Kódstruktúra

A projekt legyen tisztán szétválasztva.

Például:

```text
resiris-ide/
│
├── src/
│   ├── editor/
│   ├── autocomplete/
│   ├── diagnostics/
│   ├── project/
│   └── ui/
│
├── src-tauri/
│   ├── commands/
│   ├── project/
│   ├── runner/
│   └── main.rs
│
└── resiris-core/
    ├── lexer/
    ├── parser/
    ├── ast/
    ├── diagnostics/
    └── modules/
```

A pontos struktúra szabadon módosítható, ha az egyszerűbb vagy jobban illeszkedik a meglévő projekthez.

---

# 22. Tesztelés

Minden fontos nyelvi funkcióhoz legyen automata teszt.

Minimum:

### Include detection

```text
RSMath használva
include hiányzik
→ warning
```

### Quick Fix

```text
RSMath használva
include hiányzik
→ Quick Fix
→ include bekerül
```

### Existing include

```text
include RSMath
RSMath.sqrt(...)
→ nincs warning
```

### Unknown module

```text
include DoesNotExist
→ error
```

### Autocomplete

```text
RSMath.
→ RSMath tényleges tagjai
```

### Syntax error

Hibás Resiris kód:

```text
→ diagnostic
```

### Valid code

Érvényes Resiris:

```text
→ nincs hibajelzés
```

---

# 23. Fontos fejlesztési szabály

Ne építsd túl.

Az első cél egy működő:

```text
Resiris IDE
```

és nem:

```text
Ultimate Resiris Development Platform 3000
```

Először:

```text
editor
+
parser
+
diagnostics
+
autocomplete
+
include quick fix
+
run
```

Ha ez stabil, akkor lehet továbbmenni.

---

# 24. Fejlesztési sorrend

Javasolt sorrend:

## Phase 1

Projekt feltérképezése.

Az agent először csak vizsgálja meg:

* Resiris parser
* tokenizer
* interpreter
* modulok
* meglévő VS Code extension
* tesztek

és készítsen rövid technikai tervet.

## Phase 2

Rust/Tauri skeleton.

Egyszerű UI:

```text
editor
files
run
output
```

## Phase 3

Resiris parser integráció.

## Phase 4

Diagnostics.

## Phase 5

Autocomplete.

## Phase 6

Module resolution.

## Phase 7

Missing include warning.

## Phase 8

Quick Fix.

## Phase 9

Run / Stop.

## Phase 10

Tesztelés és stabilizálás.

---

# 25. Amit az agent NEM tehet

Ne változtassa meg önállóan:

* Resiris syntaxot
* Resiris keywordöket
* típusokat
* modul API-kat
* interpreter működését
* GameEngine működését
* input rendszert
* `START()` / `PROCESS()` működését

Ha az IDE fejlesztéséhez ilyen változtatás szükségesnek tűnik, álljon meg és jelezze.

Ne implementáljon feltételezett funkciókat.

Ne írja át a működő Resiris kódot csak stílus miatt.

---

# 26. Definition of Done – első használható verzió

Az első verzió akkor tekinthető késznek, ha:

1. Elindul Linuxon.
2. Meg tud nyitni egy Resiris projektet.
3. `.resy` fájl szerkeszthető.
4. Resiris syntax highlighting működik.
5. A tényleges Resiris parser ellenőrzi a kódot.
6. Syntax error megjelenik az editorban.
7. Modulok felismerhetők.
8. Autocomplete működik.
9. Hiányzó `include` sárga warningként megjelenik.
10. A warninghoz Quick Fix tartozik.
11. A Quick Fix ténylegesen beszúrja a szükséges `include` sort.
12. Nem generál duplikált include-ot.
13. Nem létező modul hibaként jelenik meg.
14. Resiris program futtatható.
15. Output megjelenik.
16. A fontos funkciókhoz automata tesztek vannak.
17. A meglévő Resiris projekt működését nem törte el.

---

# 27. Legfontosabb elv

Az IDE **Resiris-t értsen, ne csak Resirisnek kinéző szöveget szerkesszen.**

A végső cél:

```text
                 RESIRIS IDE
                      │
          ┌───────────┴───────────┐
          │                       │
       Editor                Language Core
                                  │
                         ┌────────┼────────┐
                         │        │        │
                       Parser   Symbols  Modules
                         │        │        │
                         └────────┼────────┘
                                  │
                         Diagnostics
                         Autocomplete
                         Quick Fix
                                  │
                              Runtime
```

Az IDE legyen egyszerű kívülről, de a háttérben a Resiris nyelv valódi struktúráját használja.

**A funkcionalitás legyen minimális, de valódi.**
