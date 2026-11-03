// The skin list: [file name, label], in picker and K order. skins.js reads only this file, so adding a skin
// never touches skins.js. A skin = skins/<name>.css (one token block, see the how-to at the top of skins.css) + one line here
// + one @import line in skins.css. The first four are the originals; the rest are the Coolors palettes.
export const SKINS = [
  ['holo', 'Holo'], ['aurora', 'Aurora'], ['amber', 'Amber'], ['paper', 'Paper'],
  ['fiery-ocean', 'Fiery Ocean'], ['ocean-blue', 'Ocean Blue'], ['olive-garden', 'Olive Garden'], ['leafy-green', 'Leafy Green'],
  ['rose-clay', 'Rose Clay'], ['autumn-harvest', 'Autumn Harvest'], ['peachy', 'Peachy Delight'], ['deep-sea', 'Deep Sea'],
  ['pastel-dream', 'Pastel Dream'], ['summer-fun', 'Summer Fun'],
];
