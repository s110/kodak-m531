// Lo único del entorno que usa el núcleo y que no es del lenguaje. Existe igual en Node, en la página y
// en el Worker; se declara aquí porque este proyecto se compila sin `lib` de DOM ni de Node.
declare class TextEncoder {
  encode(texto: string): Uint8Array<ArrayBuffer>;
}
