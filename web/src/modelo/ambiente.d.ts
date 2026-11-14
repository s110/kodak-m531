// Reloj del entorno (Node, página y Worker lo tienen); este proyecto se compila sin `lib` de DOM.
declare const performance: { now(): number };
