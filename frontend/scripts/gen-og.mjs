// Generates public/og.png (1200x630) with no dependencies: a hand-rolled PNG encoder (zlib is built in)
// and a tiny 5x7 bitmap font. Run: node scripts/gen-og.mjs   (the PNG is committed; rerun only to change it).
import { writeFileSync } from 'node:fs'
import { deflateSync } from 'node:zlib'

const W = 1200
const H = 630
const px = Buffer.alloc(W * H * 3)
const BG = [15, 15, 20]
const ACCENT = [91, 91, 214]
const FG = [243, 243, 247]
const MUTED = [168, 168, 189]

const set = (x, y, c) => {
  if (x < 0 || y < 0 || x >= W || y >= H) return
  const i = (y * W + x) * 3
  px[i] = c[0]
  px[i + 1] = c[1]
  px[i + 2] = c[2]
}
const blend = (a, b, t) => a.map((v, i) => Math.round(v * (1 - t) + b[i] * t))

// Background with a soft indigo glow in the top-right corner.
for (let y = 0; y < H; y++)
  for (let x = 0; x < W; x++) {
    const d = Math.hypot(x - 1100, y - 40) / 620
    set(x, y, blend(BG, ACCENT, Math.max(0, 1 - d) ** 2 * 0.55))
  }

// Rounded logo square with the "M" stroke (same shape as favicon.svg).
const roundRect = (x0, y0, s, r, c) => {
  for (let y = 0; y < s; y++)
    for (let x = 0; x < s; x++) {
      const cx = Math.min(Math.max(x, r), s - 1 - r)
      const cy = Math.min(Math.max(y, r), s - 1 - r)
      if (Math.hypot(x - cx, y - cy) <= r) set(x0 + x, y0 + y, c)
    }
}
const line = (x1, y1, x2, y2, w, c) => {
  const n = Math.ceil(Math.hypot(x2 - x1, y2 - y1))
  for (let i = 0; i <= n; i++) {
    const x = x1 + ((x2 - x1) * i) / n
    const y = y1 + ((y2 - y1) * i) / n
    for (let dy = -w / 2; dy <= w / 2; dy++)
      for (let dx = -w / 2; dx <= w / 2; dx++) if (Math.hypot(dx, dy) <= w / 2) set(Math.round(x + dx), Math.round(y + dy), c)
  }
}
const LX = 96
const LY = 150
roundRect(LX, LY, 128, 32, ACCENT)
const u = 128 / 32
const p = (x, y) => [LX + x * u, LY + y * u]
for (const [a, b] of [
  [[9, 22], [9, 10.5]],
  [[9, 10.5], [16, 17]],
  [[16, 17], [23, 10.5]],
  [[23, 10.5], [23, 22]],
])
  line(...p(...a), ...p(...b), 10, [255, 255, 255])

// 5x7 glyphs (only the letters we need).
const G = {
  M: ['10001', '11011', '10101', '10101', '10001', '10001', '10001'],
  N: ['10001', '11001', '10101', '10011', '10001', '10001', '10001'],
  E: ['11111', '10000', '10000', '11110', '10000', '10000', '11111'],
  O: ['01110', '10001', '10001', '10001', '10001', '10001', '01110'],
  I: ['11111', '00100', '00100', '00100', '00100', '00100', '11111'],
  C: ['01111', '10000', '10000', '10000', '10000', '10000', '01111'],
  V: ['10001', '10001', '10001', '10001', '01010', '01010', '00100'],
  R: ['11110', '10001', '10001', '11110', '10100', '10010', '10001'],
  F: ['11111', '10000', '10000', '11110', '10000', '10000', '10000'],
  A: ['01110', '10001', '10001', '11111', '10001', '10001', '10001'],
  B: ['11110', '10001', '10001', '11110', '10001', '10001', '11110'],
  L: ['10000', '10000', '10000', '10000', '10000', '10000', '11111'],
  S: ['01111', '10000', '10000', '01110', '00001', '00001', '11110'],
  W: ['10001', '10001', '10001', '10101', '10101', '11011', '10001'],
  Y: ['10001', '10001', '01010', '00100', '00100', '00100', '00100'],
  U: ['10001', '10001', '10001', '10001', '10001', '10001', '01110'],
  T: ['11111', '00100', '00100', '00100', '00100', '00100', '00100'],
  ' ': ['00000', '00000', '00000', '00000', '00000', '00000', '00000'],
}
const text = (s, x0, y0, scale, c) => {
  let x = x0
  for (const ch of s) {
    G[ch].forEach((row, ry) =>
      [...row].forEach((bit, rx) => {
        if (bit === '1') for (let dy = 0; dy < scale; dy++) for (let dx = 0; dx < scale; dx++) set(x + rx * scale + dx, y0 + ry * scale + dy, c)
      }),
    )
    x += 6 * scale
  }
}
text('MNEMONIC', 96, 330, 13, FG)
text('VERIFIABLE ANSWERS', 96, 470, 6, MUTED)
text('FROM YOUR OWN NOTES', 96, 530, 6, MUTED)

// PNG container: signature + IHDR + IDAT (filter byte 0 per row) + IEND.
const crcTable = Array.from({ length: 256 }, (_, n) => {
  let c = n
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
  return c >>> 0
})
const crc = (buf) => {
  let c = 0xffffffff
  for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}
const chunk = (type, data) => {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const body = Buffer.concat([Buffer.from(type), data])
  const sum = Buffer.alloc(4)
  sum.writeUInt32BE(crc(body))
  return Buffer.concat([len, body, sum])
}
const ihdr = Buffer.alloc(13)
ihdr.writeUInt32BE(W, 0)
ihdr.writeUInt32BE(H, 4)
ihdr[8] = 8 // bit depth
ihdr[9] = 2 // RGB
const raw = Buffer.alloc((W * 3 + 1) * H)
for (let y = 0; y < H; y++) px.copy(raw, y * (W * 3 + 1) + 1, y * W * 3, (y + 1) * W * 3)
writeFileSync(
  new URL('../public/og.png', import.meta.url),
  Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]),
)
console.log('wrote public/og.png')
