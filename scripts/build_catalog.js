// scripts/build_catalog.js
// Genera data/catalogo_engagement.json desde catalogoTN.csv
// Uso: node scripts/build_catalog.js [ruta-al-csv]

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, "..");

const CSV_PATH = process.argv[2] || "C:\\Users\\PC Midi\\Downloads\\catalogoTN.csv";
const OUTPUT_PATH = path.join(ROOT, "data", "catalogo_engagement.json");

const CATEGORIAS_MUSICALES = [
  "Controladores MIDI",
  "Sintetizadores",
  "Interfaces",
  "Micrófonos",
  "Baterías Electrónicas",
  "Auriculares y monitores",
  "Organos y Pianos",
  "Instrumentos de Cuerda",
  "Multimedia / Gamer",
];

const CATEGORIAS_EXCLUIR = ["Mochilas", "Cámaras", "Cables", "PREVENTA", "Instrumentos de Cuerda", "Multimedia / Gamer"];

function stripHtml(html) {
  if (!html) return "";
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&oacute;/g, "ó")
    .replace(/&aacute;/g, "á")
    .replace(/&eacute;/g, "é")
    .replace(/&iacute;/g, "í")
    .replace(/&uacute;/g, "ú")
    .replace(/&ntilde;/g, "ñ")
    .replace(/&Aacute;/g, "Á")
    .replace(/&Eacute;/g, "É")
    .replace(/&Iacute;/g, "Í")
    .replace(/&Oacute;/g, "Ó")
    .replace(/&Uacute;/g, "Ú")
    .replace(/&Ntilde;/g, "Ñ")
    .replace(/&uuml;/g, "ü")
    .replace(/&ldquo;/g, '"')
    .replace(/&rdquo;/g, '"')
    .replace(/&lsquo;/g, "'")
    .replace(/&rsquo;/g, "'")
    .replace(/&mdash;/g, "—")
    .replace(/&ndash;/g, "–")
    .replace(/&iquest;/g, "¿")
    .replace(/&iexcl;/g, "¡")
    .replace(/&deg;/g, "°")
    .replace(/&frac12;/g, "½")
    .replace(/&times;/g, "×")
    .replace(/&#\d+;/g, "")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function parseCsv(content) {
  const lines = content.split("\n");
  const headers = lines[0].split(";").map(h => h.trim().replace(/^"/, "").replace(/"$/, ""));

  const rows = [];
  let currentRow = "";
  let inQuotes = false;

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];

    for (const char of line) {
      if (char === '"') inQuotes = !inQuotes;
      currentRow += char;
    }

    if (!inQuotes) {
      if (currentRow.trim()) {
        const cols = splitCsvRow(currentRow);
        if (cols.length >= 3) {
          const row = {};
          headers.forEach((h, idx) => {
            row[h] = (cols[idx] || "").trim().replace(/^"/, "").replace(/"$/, "");
          });
          rows.push(row);
        }
      }
      currentRow = "";
    } else {
      currentRow += "\n";
    }
  }

  return rows;
}

function splitCsvRow(row) {
  const cols = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < row.length; i++) {
    const char = row[i];
    if (char === '"') {
      if (inQuotes && row[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ";" && !inQuotes) {
      cols.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  cols.push(current);
  return cols;
}

function isMusicCategory(categoria) {
  if (!categoria) return false;
  const catLower = categoria.toLowerCase();

  for (const excluir of CATEGORIAS_EXCLUIR) {
    if (catLower.includes(excluir.toLowerCase())) return false;
  }

  for (const musical of CATEGORIAS_MUSICALES) {
    if (catLower.includes(musical.toLowerCase())) return true;
  }

  // Excluir explícitamente categorías no musicales
  if (catLower.includes("mochila") || catLower.includes("camara") || catLower.includes("camera")) return false;

  return false;
}

// Main
console.log(`📂 Leyendo CSV: ${CSV_PATH}`);

let content;
try {
  const buf = fs.readFileSync(CSV_PATH);
  // Intentar decodificar como latin1/cp1252 ya que el CSV viene de Windows
  content = buf.toString("latin1");
} catch (e) {
  console.error(`❌ No se pudo leer el CSV: ${e.message}`);
  process.exit(1);
}

console.log(`📋 Parseando...`);
const rows = parseCsv(content);
console.log(`✅ ${rows.length} filas parseadas`);

const catalog = [];

for (const row of rows) {
  const nombre = row["Nombre"] || row["Nombre "] || "";
  const categoria = row["Categorías"] || row["Categorias"] || row["Categor\xedas"] || "";
  const marca = row["Marca"] || "";
  const descripcionHtml = row["Descripción"] || row["Descripcion"] || row["Descripci\xf3n"] || "";
  const sku = row["SKU"] || "";

  if (!nombre || !isMusicCategory(categoria)) continue;

  // Limpiar nombre (remover "PREVENTA" del nombre)
  const nombreLimpio = nombre.replace(/^PREVENTA\s+/i, "").trim();

  const descripcionLimpia = stripHtml(descripcionHtml);

  // Categoría principal (antes del ">")
  const catPrincipal = categoria.split(">")[0].trim();

  catalog.push({
    nombre: nombreLimpio,
    categoria: catPrincipal,
    marca: marca.trim(),
    sku: sku.trim(),
    descripcion: descripcionLimpia,
  });
}

console.log(`\n🎵 Productos musicales filtrados: ${catalog.length}`);

// Resumen por categoría
const cats = {};
for (const p of catalog) {
  cats[p.categoria] = (cats[p.categoria] || 0) + 1;
}
for (const [cat, count] of Object.entries(cats).sort()) {
  console.log(`  ${cat}: ${count}`);
}

// Guardar
fs.writeFileSync(OUTPUT_PATH, JSON.stringify(catalog, null, 2), "utf-8");
console.log(`\n✅ Catálogo guardado en: ${OUTPUT_PATH}`);
console.log(`   Total: ${catalog.length} productos listos para el agente de engagement`);
