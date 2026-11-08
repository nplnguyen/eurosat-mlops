const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require("./apply_theme.js");

const THEME = {
  name: "EuroSAT Orbit",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0E1E2B", lt1: "FFFFFF", dk2: "3C5566", lt2: "EEF3F1",
    accent1: "3A8F5C", accent2: "E3A13B", accent3: "2F6E9E",
    accent4: "8C6A43", accent5: "C2533F", accent6: "7AA6A1",
    hlink: "2F6E9E", folHlink: "7AA6A1",
  },
};
const HEX = THEME.colors;
const OUT = process.argv[2] || "soutenance-mlops-eurosat.pptx";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "EuroSAT en production — soutenance MLOps";
pres.author = "Binôme M2 Data Engineering & IA";
const C = pres.SchemeColor;
const W = 13.333;

// ------------------------------------------------------------------ layouts
pres.defineSlideMaster({
  title: "TITRE_SOMBRE",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.7, y: 2.0, w: 7.2, h: 1.6,
      fontFace: THEME.headFontFace, fontSize: 44, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 },
      text: "Titre" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.7, y: 3.8, w: 7.2, h: 2.4,
      fontFace: THEME.bodyFontFace, fontSize: 18, color: C.accent6, valign: "top", margin: 0 },
      text: "Sous-titre" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENU",
  background: { color: C.background1 },
  margin: [0.5, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.9,
      fontFace: THEME.headFontFace, fontSize: 32, bold: true, color: C.text1, valign: "middle", align: "left", margin: 0 },
      text: "Titre" } },
    { text: { text: "EuroSAT MLOps · M2 Data Engineering & IA",
      options: { x: 0.6, y: 7.0, w: 6, h: 0.3, fontFace: THEME.bodyFontFace, fontSize: 10, color: C.text2, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.0, w: 0.5, h: 0.3, fontFace: THEME.bodyFontFace, fontSize: 10, color: C.text2, align: "right" },
});

// ------------------------------------------------------------------ helpers
const iconCache = {};
async function iconPng(name, color = "FFFFFF") {
  const key = name + color;
  if (!iconCache[key]) {
    const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(fa[name], { color: "#" + color, size: 256 }));
    iconCache[key] = "image/png;base64," + (await sharp(Buffer.from(svg)).png().toBuffer()).toString("base64");
  }
  return iconCache[key];
}
async function iconCircle(slide, name, x, y, d, fill) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" }, objectName: `icone-${name}` });
  const p = d * 0.25;
  slide.addImage({ data: await iconPng(name), x: x + p, y: y + p, w: d - 2 * p, h: d - 2 * p, altText: name });
}
function card(slide, x, y, w, h, fill = C.background2, name = "carte") {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { type: "none" }, objectName: name,
  });
}
function txt(slide, text, opts) {
  slide.addText(text, Object.assign({ isTextBox: true, margin: 0, fontSize: 14, color: C.text1, valign: "top" }, opts));
}
// Flèche du point (x1, y1) au point (x2, y2) ; largeur/hauteur toujours positives (flip sinon)
function seg(slide, x1, y1, x2, y2, color = C.text2, width = 1.75) {
  slide.addShape(pres.shapes.LINE, {
    x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    flipH: x2 < x1, flipV: y2 < y1, line: { color, width, endArrowType: "triangle" },
  });
}
function arrow(slide, x, y, w, color = C.text2) { seg(slide, x, y, x + w, y, color); }
function vArrow(slide, x, y, h, color = C.text2) { seg(slide, x, y, x, y + h, color); }
function content(title, section) {
  const s = pres.addSlide({ masterName: "CONTENU", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  return s;
}
const TODO = { italic: true, color: C.accent5 };
function tableStyle(rows, colW, x, y, opts = {}) {
  return { x, y, w: colW.reduce((a, b) => a + b, 0), colW, fontFace: THEME.bodyFontFace, fontSize: 14,
    color: C.text1, border: { type: "solid", pt: 0.75, color: "C9D5D0" }, rowH: opts.rowH || 0.45, valign: "middle", ...opts };
}
const head = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text1 } } });

// Couleurs de classes (mosaïque, motif visuel du deck)
const CLASSES = [
  ["AnnualCrop", "Cultures annuelles", "C9B458"], ["Forest", "Forêt", "2F6B3F"],
  ["HerbaceousVegetation", "Végétation herbacée", "7FA65A"], ["Highway", "Autoroute", "7D7F82"],
  ["Industrial", "Industriel", "A35D4A"], ["Pasture", "Pâturage", "9CC27A"],
  ["PermanentCrop", "Cultures permanentes", "B08A3E"], ["Residential", "Résidentiel", "C98A6B"],
  ["River", "Rivière", "3A7CA5"], ["SeaLake", "Mer / lac", "1F4E79"],
];

(async () => {
  // ================================================================ 1. Titre
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "TITRE_SOMBRE", sectionTitle: "Introduction" });
  s.addText("EuroSAT en production", { placeholder: "title" });
  s.addText([
    { text: "Mise en production d'un classifieur d'occupation des sols à partir d'images Sentinel-2", options: { breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 10 } },
    { text: "Projet MLOps · M2 Data Engineering & IA", options: { breakLine: true, color: C.background1, fontSize: 16 } },
    { text: "NOM Prénom & NOM Prénom · 2026-2027", options: { color: C.background1, fontSize: 16 } },
  ], { placeholder: "body" });
  // mosaïque de tuiles
  CLASSES.forEach((c, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const sz = 1.25, gap = 0.18;
    if (row > 3) return;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 8.75 + col * (sz + gap), y: 1.1 + row * (sz + gap) + (col === 1 ? 0.45 : 0), w: sz, h: sz,
      rectRadius: 0.1, fill: { color: c[2] }, line: { type: "none" }, objectName: `tuile-${c[0]}`,
    });
  });
  s.addNotes("Présentation du binôme et du sujet. Notre objectif n'est pas seulement d'entraîner un modèle, mais de construire tout le système qui le met en production : déploiement, sécurité, supervision et cycle de vie des versions.");

  // ================================================================ 2. Cas d'usage
  s = content("Le cas d'usage : cartographier l'occupation des sols", "Introduction");
  const stats = [["27 000", "images Sentinel-2 (EuroSAT)"], ["10", "classes d'occupation des sols"], ["64 × 64", "pixels, 10 m par pixel"]];
  stats.forEach(([v, l], i) => {
    const y = 1.55 + i * 1.65;
    txt(s, v, { x: 0.6, y, w: 4.6, h: 0.85, fontSize: 48, bold: true, color: C.accent1, fontFace: THEME.headFontFace, valign: "bottom" });
    txt(s, l, { x: 0.6, y: y + 0.9, w: 4.6, h: 0.4, fontSize: 16, color: C.text2 });
  });
  CLASSES.forEach((c, i) => {
    const col = i % 5, row = Math.floor(i / 5);
    const x = 5.6 + col * 1.45, y = 1.7 + row * 2.45;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 1.3, h: 1.3, rectRadius: 0.1, fill: { color: c[2] }, line: { type: "none" }, objectName: `tuile-${c[0]}` });
    txt(s, c[1], { x: x - 0.05, y: y + 1.38, w: 1.4, h: 0.7, fontSize: 12, align: "center", color: C.text1 });
  });
  txt(s, "Cas réel avec un drift naturel : saisons, nuages, capteur, nouvelles régions.",
    { x: 5.6, y: 6.35, w: 7.1, h: 0.4, fontSize: 14, italic: true, color: C.text2 });
  s.addNotes("EuroSAT (Helber et al., 2019) : 27 000 tuiles de 34 pays européens. Le jeu n'est pas trivial : AnnualCrop, PermanentCrop et Pasture se ressemblent, tout comme Highway et River. C'est aussi un cas où le data drift est naturel, ce qui justifie le monitoring. Enfin, sa taille permet d'entraîner sur CPU, donc de lancer le système de zéro.");

  // ================================================================ 3. Couverture grille
  s = content("Les 4 niveaux de la grille sont couverts", "Introduction");
  const lv = [
    ["Niveau 0", "FaDocker", C.accent3, ["10 conteneurs", "Une commande : make up", "1er modèle entraîné automatiquement"]],
    ["Niveau 1", "FaUserShield", C.accent1, ["Déploiement VM (script + CD)", "Header X-API-Key obligatoire", "Usage tracé par utilisateur", "Test de charge Locust"]],
    ["Niveau 2", "FaChartLine", C.accent2, ["VM créée par Terraform", "UI Streamlit", "Détection de data drift", "MLflow : versions + mise à jour"]],
    ["Niveau 3", "FaRocket", C.accent5, ["Quantization INT8", "Canary deployment 90/10", "Scaling horizontal", "Kubernetes + HPA"]],
  ];
  for (let i = 0; i < lv.length; i++) {
    const [t, ic, col, items] = lv[i];
    const x = 0.6 + i * 3.08, y = 1.55, w = 2.85, h = 5.1;
    card(s, x, y, w, h, C.background2, `carte-${t}`);
    await iconCircle(s, ic, x + 0.3, y + 0.35, 0.8, col);
    txt(s, t, { x: x + 0.3, y: y + 1.35, w: w - 0.6, h: 0.5, fontSize: 22, bold: true, fontFace: THEME.headFontFace });
    s.addText(items.map((it, k) => ({ text: it, options: { bullet: true, breakLine: k < items.length - 1 } })),
      { isTextBox: true, x: x + 0.3, y: y + 2.0, w: w - 0.5, h: 2.9, fontSize: 15, color: C.text1, valign: "top", margin: 0, paraSpaceAfter: 8 });
  }
  s.addNotes("Vue d'ensemble : chaque exigence de la grille correspond à une brique du dépôt. Le tableau de correspondance détaillé, avec les fichiers, est dans le README. La suite suit l'ordre modèle, architecture, puis les niveaux.");

  // ================================================================ 4. Pipeline modèle
  pres.addSection({ title: "Modèle" });
  s = content("Un modèle léger, quantifié et traçable", "Modèle");
  const steps = [
    ["FaDatabase", "Données", "Split stratifié\n70 / 15 / 15"],
    ["FaBrain", "ResNet-18", "Transfer learning\nImageNet → 10 classes"],
    ["FaCubes", "Export ONNX", "Sorties : logits\n+ embedding 512-d"],
    ["FaTachometerAlt", "INT8", "Quantization statique\nQDQ par canal"],
    ["FaCheck", "Quality gate", "F1 macro test\n≥ 0,85"],
    ["FaCodeBranch", "MLflow", "Version enregistrée\nalias « challenger »"],
  ];
  for (let i = 0; i < steps.length; i++) {
    const [ic, t, d] = steps[i];
    const x = 0.6 + i * 2.07, y = 1.7;
    card(s, x, y, 1.8, 2.75, C.background2, `etape-${t}`);
    await iconCircle(s, ic, x + 0.5, y + 0.3, 0.8, i === 3 ? C.accent2 : C.accent1);
    txt(s, t, { x: x + 0.1, y: y + 1.25, w: 1.6, h: 0.45, fontSize: 17, bold: true, align: "center" });
    txt(s, d, { x: x + 0.1, y: y + 1.75, w: 1.6, h: 0.9, fontSize: 13, align: "center", color: C.text2 });
    if (i < steps.length - 1) arrow(s, x + 1.82, y + 1.37, 0.23);
  }
  const notes3 = [
    ["Augmentations adaptées", "Rotations de 90° et symétries : une image satellite n'a pas d'orientation."],
    ["Entraînement", "AdamW, cosine annealing, label smoothing 0,1, early stopping sur le F1."],
    ["Serving sans PyTorch", "onnxruntime seul ; le prétraitement est versionné avec le modèle."],
  ];
  notes3.forEach(([t, d], i) => {
    const x = 0.6 + i * 4.1;
    txt(s, t, { x, y: 4.85, w: 3.8, h: 0.4, fontSize: 16, bold: true, color: C.accent1 });
    txt(s, d, { x, y: 5.3, w: 3.8, h: 1.1, fontSize: 14, color: C.text1 });
  });
  s.addNotes("Le modèle renvoie deux sorties : les logits et l'embedding de l'avant-dernière couche. L'embedding alimente la détection de drift sans second passage dans le réseau. La quantization statique est calibrée sur 512 images de validation. Une version n'entre dans le registre que si elle passe la quality gate. Point clé : le prétraitement (taille, moyenne, écart-type) est exporté avec le modèle pour éviter le training/serving skew.");

  // ================================================================ 5. Résultats modèle
  s = content("Résultats : FP32 vs INT8 sur le jeu de test", "Modèle");
    const g = (t) => ({ text: t, options: { bold: true, color: C.accent1 } });
  s.addTable([
    [head("Métrique"), head("FP32"), head("INT8"), head("Écart")],
    ["Accuracy", "95,47 %", "95,64 %", "+0,2 pt"],
    ["F1 macro", "0,953", "0,955", "+0,002"],
    ["Taille (Mo)", "44,7", "11,3", g("÷ 4,0")],
    ["Latence p50 (ms)", "8,7", "2,1", g("× 4,2 plus rapide")],
    ["Latence p95 (ms)", "32,4", "4,4", g("× 7,3 plus rapide")],
  ], tableStyle(null, [2.0, 1.3, 1.3, 1.9], 0.6, 1.6, { rowH: 0.62 }));
  s.addImage({ path: require("path").join(__dirname, "confusion_matrix.png"), x: 7.55, y: 1.45, w: 5.175, h: 4.6,
    altText: "Matrice de confusion normalisée du modèle INT8 sur le jeu de test" });
  txt(s, "Modèle de bootstrap : ResNet-18, 3 époques sur 30 % des données, test n = 1 215, CPU (Docker, MacBook Air). Référence publiée : ≈ 98,6 % (ResNet-50, Helber et al., 2019).",
    { x: 0.6, y: 5.55, w: 6.5, h: 0.9, fontSize: 13, italic: true, color: C.text2 });
  s.addNotes("Résultats du modèle de bootstrap : déjà 95,6 % d'accuracy après 3 époques sur 30 % des données. La quantization INT8 divise la taille par 4 et la latence médiane par 4,2 sans perte de précision ; le léger gain d'INT8 (+0,2 pt) est dans le bruit statistique sur 1 215 images. Matrice de confusion : les deux confusions principales sont PermanentCrop prise pour HerbaceousVegetation (8 %) et Highway prise pour River (7 %, deux structures linéaires), conformément à ce qu'on attendait. Residential et SeaLake sont parfaitement reconnues. Un entraînement complet (make train EPOCHS=10) devrait se rapprocher de la référence publiée.");

  const r = (t) => ({ text: t, options: TODO });
  // ================================================================ 6. Architecture
  pres.addSection({ title: "Système" });
  s = content("Architecture : 10 conteneurs lancés en une commande", "Système");
  const box = (t, sub, x, y, w, h, fill, fc = C.background1) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1, fill: { color: fill }, line: { type: "none" }, objectName: `bloc-${t}` });
    s.addText([{ text: t, options: { bold: true, fontSize: 14, breakLine: !!sub } }].concat(sub ? [{ text: sub, options: { fontSize: 11 } }] : []),
      { isTextBox: true, x, y, w, h, align: "center", valign: "middle", color: fc, margin: 2 });
  };
  box("Clients", "UI · curl · Locust", 0.6, 3.25, 1.7, 1.0, C.text2);
  box("Gateway nginx", "split canary", 2.85, 3.25, 1.9, 1.0, C.text1);
  box("api-stable ×N", "alias champion", 5.35, 2.15, 2.2, 0.95, C.accent1);
  box("api-canary", "alias challenger", 5.35, 4.4, 2.2, 0.95, C.accent2, C.text1);
  box("Streamlit UI", null, 2.85, 1.75, 1.9, 0.7, C.accent3);
  box("PostgreSQL", "users · usage", 8.4, 1.55, 2.0, 0.85, C.accent6, C.text1);
  box("Redis", "quotas · drift", 8.4, 2.6, 2.0, 0.85, C.accent6, C.text1);
  box("MLflow", "tracking · registry", 8.4, 3.65, 2.0, 0.85, C.accent3);
  box("Artefacts", "volume (S3 en cloud)", 10.75, 3.65, 1.95, 0.85, C.accent6, C.text1);
  box("Trainer", "PyTorch → ONNX INT8", 8.4, 5.3, 2.0, 0.9, C.accent4);
  box("Prometheus", "scrape /metrics", 5.35, 5.85, 2.2, 0.75, C.text2);
  box("Grafana", "dashboard · alertes", 2.85, 5.85, 1.9, 0.75, C.text2);
  arrow(s, 2.32, 3.75, 0.5);
  seg(s, 4.77, 3.6, 5.33, 2.65); seg(s, 4.77, 3.9, 5.33, 4.85);
  txt(s, "90 %", { x: 5.12, y: 3.12, w: 0.6, h: 0.3, fontSize: 11, bold: true, color: C.accent1 });
  txt(s, "10 %", { x: 5.12, y: 3.98, w: 0.6, h: 0.3, fontSize: 11, bold: true, color: C.accent2 });

  vArrow(s, 3.8, 2.47, 0.76);
  arrow(s, 7.57, 2.6, 0.8); arrow(s, 7.57, 4.1, 0.8);
  arrow(s, 10.42, 4.07, 0.31);
  vArrow(s, 9.4, 5.28, -0.76);
  arrow(s, 5.33, 6.22, -0.56);
  vArrow(s, 6.45, 5.83, -0.46);
  card(s, 10.75, 5.3, 1.95, 1.3, C.text1, "commande");
  txt(s, "$ make up", { x: 10.9, y: 5.55, w: 1.7, h: 0.4, fontSize: 18, bold: true, color: C.accent2, fontFace: "Courier New" });
  txt(s, "= docker compose\nup -d --build", { x: 10.9, y: 5.95, w: 1.7, h: 0.6, fontSize: 11, color: C.background1, fontFace: "Courier New" });
  s.addNotes("Le principe structurant : l'image de l'API ne contient aucun modèle. Elle connaît seulement un alias MLflow, interroge le registre toutes les 30 secondes et recharge la nouvelle version à chaud. Livrer du code et livrer un modèle deviennent deux opérations indépendantes. L'API est sans état : quotas et fenêtre de drift sont dans Redis, l'usage dans PostgreSQL, ce qui permet de la répliquer. Le serveur MLflow sert de proxy vers le stockage des artefacts : les clients n'ont besoin que de son URL.");

  // ================================================================ 7. Sécurité
  s = content("Chaque requête est authentifiée, limitée et tracée", "Système");
  const sec = [
    ["FaKey", "Header X-API-Key", "ou Authorization: Bearer"],
    ["FaLock", "Empreinte HMAC", "clé jamais stockée en clair"],
    ["FaBalanceScale", "Quota par minute", "compteur Redis partagé"],
    ["FaBrain", "Inférence ONNX", "INT8, quelques ms"],
    ["FaDatabase", "Journal d'usage", "écriture par lots (1 s)"],
  ];
  for (let i = 0; i < sec.length; i++) {
    const [ic, t, d] = sec[i];
    const x = 0.6 + i * 2.5;
    await iconCircle(s, ic, x + 0.6, 1.6, 0.95, C.accent1);
    txt(s, t, { x, y: 2.75, w: 2.15, h: 0.45, fontSize: 16, bold: true, align: "center" });
    txt(s, d, { x, y: 3.2, w: 2.15, h: 0.6, fontSize: 13, align: "center", color: C.text2 });
    if (i < sec.length - 1) arrow(s, x + 1.7, 2.08, 0.7);
  }
  const codes = [["401", "Clé absente ou révoquée", C.accent5], ["429", "Quota dépassé, réessayer dans la minute", C.accent2], ["200", "Prédiction + version servie", C.accent1]];
  codes.forEach(([c, d, col], i) => {
    const x = 0.6 + i * 4.1;
    card(s, x, 4.35, 3.8, 1.55, C.background2, `code-${c}`);
    txt(s, c, { x: x + 0.3, y: 4.5, w: 1.4, h: 1.2, fontSize: 44, bold: true, color: col, fontFace: THEME.headFontFace, valign: "middle" });
    txt(s, d, { x: x + 1.7, y: 4.5, w: 1.9, h: 1.2, fontSize: 14, valign: "middle" });
  });
  txt(s, "Usage consultable : /v1/me/usage (utilisateur), /admin/usage (admin), Grafana par utilisateur",
    { x: 0.6, y: 6.2, w: 12.1, h: 0.4, fontSize: 14, italic: true, color: C.text2 });
  s.addNotes("Les clés sont générées avec 256 bits d'aléa. En base, on ne stocke que leur empreinte HMAC avec un pepper serveur : une fuite de la base ne donne pas les clés. Un cache de 30 s évite une requête SQL par appel. Les administrateurs créent, révoquent et font tourner les clés. Le journal d'usage est écrit par lots pour ne pas ralentir les requêtes. Démo possible : curl sans clé, puis avec clé.");

  // ================================================================ 8. CD + Terraform
  s = content("Déploiement continu sur une VM créée par Terraform", "Système");
  txt(s, "Infrastructure as code (AWS, Paris)", { x: 0.6, y: 1.5, w: 6, h: 0.4, fontSize: 18, bold: true, color: C.accent3 });
  const tf = [["EC2 t3.xlarge", "Ubuntu 24.04, disque chiffré"], ["Security group", "HTTP public, SSH restreint"], ["IP élastique", "adresse stable pour la CD"], ["cloud-init", "Docker + SSH durci + fail2ban"]];
  tf.forEach(([t, d], i) => {
    const x = 0.6 + i * 3.08;
    card(s, x, 2.0, 2.85, 1.25, C.background2, `tf-${t}`);
    txt(s, t, { x: x + 0.2, y: 2.15, w: 2.5, h: 0.4, fontSize: 16, bold: true });
    txt(s, d, { x: x + 0.2, y: 2.6, w: 2.5, h: 0.55, fontSize: 13, color: C.text2 });
  });
  txt(s, "Pipeline GitHub Actions (tag v*.*.*)", { x: 0.6, y: 3.65, w: 6, h: 0.4, fontSize: 18, bold: true, color: C.accent1 });
  const cd = [["FaCodeBranch", "git tag v1.0.0"], ["FaCheck", "CI : lint, tests, IaC"], ["FaDocker", "Build + push GHCR"], ["FaServer", "SSH : compose pull / up"], ["FaSearch", "Smoke test 401 / 200"]];
  for (let i = 0; i < cd.length; i++) {
    const [ic, t] = cd[i];
    const x = 0.6 + i * 2.5;
    await iconCircle(s, ic, x + 0.65, 4.2, 0.85, C.text1);
    txt(s, t, { x, y: 5.2, w: 2.15, h: 0.7, fontSize: 14, align: "center", bold: true });
    if (i < cd.length - 1) arrow(s, x + 1.65, 4.62, 0.8);
  }
  txt(s, "Alternative manuelle : ./scripts/deploy.sh ubuntu@IP v1.0.0 · MLflow et Grafana ne sont accessibles que par tunnel SSH",
    { x: 0.6, y: 6.15, w: 12.1, h: 0.5, fontSize: 13, italic: true, color: C.text2 });
  s.addNotes("La VM ne compile rien : elle tire des images construites par la CI. Le smoke test vérifie à la fois que le service répond et que la sécurité est active (une requête sans clé doit recevoir 401). En production, seuls les ports 80/443 sont ouverts ; les outils d'administration sont liés à 127.0.0.1.");

  // ================================================================ 9. MLflow & canary
  pres.addSection({ title: "Cycle de vie" });
  s = content("MLflow pilote la production par alias", "Cycle de vie");
  txt(s, "Model Registry", { x: 0.6, y: 1.5, w: 4, h: 0.4, fontSize: 18, bold: true, color: C.accent3 });
  const vers = [["v1", "previous-champion", C.text2], ["v2", "champion", C.accent1], ["v3", "challenger", C.accent2]];
  vers.forEach(([v, a, col], i) => {
    const y = 2.05 + i * 1.15;
    card(s, 0.6, y, 4.3, 0.95, C.background2, `version-${v}`);
    txt(s, v, { x: 0.85, y, w: 0.8, h: 0.95, fontSize: 24, bold: true, valign: "middle", fontFace: THEME.headFontFace });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 1.85, y: y + 0.24, w: 2.8, h: 0.48, rectRadius: 0.24, fill: { color: col }, line: { type: "none" }, objectName: `alias-${a}` });
    txt(s, a, { x: 1.85, y: y + 0.24, w: 2.8, h: 0.48, fontSize: 14, bold: true, align: "center", valign: "middle", color: i === 2 ? C.text1 : C.background1 });
  });
  // split
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.0, y: 2.6, w: 1.9, h: 1.0, rectRadius: 0.1, fill: { color: C.text1 }, line: { type: "none" }, objectName: "gateway" });
  txt(s, "Gateway", { x: 6.0, y: 2.6, w: 1.9, h: 1.0, fontSize: 16, bold: true, align: "center", valign: "middle", color: C.background1 });
  seg(s, 7.9, 2.85, 8.95, 2.15, C.accent1, 4);
  seg(s, 7.9, 3.35, 8.95, 4.05, C.accent2, 1.5);
  card(s, 9.0, 1.55, 3.7, 1.15, C.accent1, "stable");
  txt(s, [{ text: "90 %  api-stable", options: { bold: true, fontSize: 18, breakLine: true } }, { text: "sert « champion » (v2)", options: { fontSize: 13 } }],
    { x: 9.25, y: 1.55, w: 3.3, h: 1.15, valign: "middle", color: C.background1 });
  card(s, 9.0, 3.5, 3.7, 1.15, C.accent2, "canary");
  txt(s, [{ text: "10 %  api-canary", options: { bold: true, fontSize: 18, breakLine: true } }, { text: "sert « challenger » (v3)", options: { fontSize: 13 } }],
    { x: 9.25, y: 3.5, w: 3.3, h: 1.15, valign: "middle", color: C.text1 });
  // procédure
  const proc = [["1", "make train", "nouvelle version → challenger"], ["2", "Rechargement à chaud", "le canary la sert en < 30 s"], ["3", "Comparaison Grafana", "latence, erreurs, confiance, drift"], ["4", "make promote / rollback", "simple changement d'alias"]];
  proc.forEach(([n, t, d], i) => {
    const x = 0.6 + i * 3.08;
    s.addShape(pres.shapes.OVAL, { x, y: 5.75, w: 0.55, h: 0.55, fill: { color: C.text1 }, line: { type: "none" }, objectName: `num-${n}` });
    txt(s, n, { x, y: 5.75, w: 0.55, h: 0.55, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle" });
    txt(s, t, { x: x + 0.7, y: 5.7, w: 2.25, h: 0.4, fontSize: 15, bold: true });
    txt(s, d, { x: x + 0.7, y: 6.1, w: 2.25, h: 0.7, fontSize: 13, color: C.text2 });
  });
  s.addNotes("Les services ne connaissent pas de numéro de version, seulement un alias. Promouvoir ou annuler revient à déplacer un alias : aucun redéploiement de conteneur. Le header X-Canary: always permet de forcer le canary pour la démo. Sous Kubernetes, le même mécanisme passe par les annotations canary d'ingress-nginx.");

  // ================================================================ 10. Drift
  s = content("Détection de data drift sur les embeddings", "Cycle de vie");
  const dsteps = [
    ["Référence", "Embeddings 512-d du jeu de validation, stockés avec le modèle"],
    ["Réduction", "ACP ajustée sur la référence : k = 10 composantes"],
    ["Test", "Kolmogorov-Smirnov par composante, fenêtre des 1 000 dernières requêtes"],
    ["Décision", "Drift si une p-value < α / k (Bonferroni, α = 0,05)"],
  ];
  dsteps.forEach(([t, d], i) => {
    const y = 1.6 + i * 1.2;
    s.addShape(pres.shapes.OVAL, { x: 0.6, y, w: 0.7, h: 0.7, fill: { color: C.accent3 }, line: { type: "none" }, objectName: `drift-${i + 1}` });
    txt(s, String(i + 1), { x: 0.6, y, w: 0.7, h: 0.7, fontSize: 20, bold: true, color: C.background1, align: "center", valign: "middle" });
    txt(s, t, { x: 1.55, y: y - 0.02, w: 5.3, h: 0.4, fontSize: 17, bold: true });
    txt(s, d, { x: 1.55, y: y + 0.38, w: 5.3, h: 0.65, fontSize: 14, color: C.text2 });
  });
  card(s, 7.4, 1.6, 5.3, 2.15, C.background2, "indicateurs");
  txt(s, "Indicateurs complémentaires", { x: 7.7, y: 1.75, w: 4.8, h: 0.4, fontSize: 17, bold: true, color: C.accent3 });
  s.addText([
    { text: "PSI des classes prédites (drift de prédiction)", options: { bullet: true, breakLine: true } },
    { text: "Confiance moyenne (sortie du domaine)", options: { bullet: true, breakLine: true } },
    { text: "Jauges Prometheus + alerte au bout de 5 min", options: { bullet: true } },
  ], { isTextBox: true, x: 7.7, y: 2.25, w: 4.8, h: 1.4, fontSize: 14, color: C.text1, margin: 0, paraSpaceAfter: 6, valign: "top" });
  txt(s, "Démo : perturbations simulées", { x: 7.4, y: 4.05, w: 5.3, h: 0.4, fontSize: 17, bold: true });
  const pert = [["Nuages", "E8EEF2"], ["Flou", "D3DCE2"], ["Bruit", "BFC9D1"], ["Sous-exposition", "8C9AA5"], ["Sursaturation", "C7A86B"], ["Contrôle", "3A8F5C"]];
  pert.forEach(([p, col], i) => {
    const x = 7.4 + (i % 3) * 1.8, y = 4.6 + Math.floor(i / 3) * 0.85;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 1.65, h: 0.65, rectRadius: 0.1, fill: { color: col }, line: { type: "none" }, objectName: `pert-${p}` });
    txt(s, p, { x, y, w: 1.65, h: 0.65, fontSize: 13, bold: true, align: "center", valign: "middle", color: i === 5 ? C.background1 : C.text1 });
  });
  s.addNotes("Tester les pixels directement serait peu fiable (grande dimension, forte corrélation spatiale). On suit l'approche de Rabanser et al. (2019) : réduire les représentations internes puis faire des tests univariés avec correction de Bonferroni. La fenêtre est stockée dans Redis : tous les réplicas contribuent au même échantillon. Limite à mentionner : un drift n'est pas forcément une baisse de précision, car on n'a pas les vraies étiquettes en production.");

  // ================================================================ 11. Scaling / k8s
  s = content("Passer à l'échelle : une API sans état", "Cycle de vie");
  card(s, 0.6, 1.55, 5.7, 4.9, C.background2, "compose");
  await iconCircle(s, "FaDocker", 0.9, 1.8, 0.8, C.accent3);
  txt(s, "Docker Compose (VM)", { x: 1.9, y: 1.9, w: 4.2, h: 0.6, fontSize: 20, bold: true, valign: "middle" });
  txt(s, "$ make scale N=3", { x: 0.9, y: 2.9, w: 5.2, h: 0.45, fontSize: 18, bold: true, fontFace: "Courier New", color: C.accent1 });
  s.addText([
    { text: "nginx répartit en round-robin sur les réplicas", options: { bullet: true, breakLine: true } },
    { text: "Prometheus les découvre par DNS", options: { bullet: true, breakLine: true } },
    { text: "Quotas, fenêtre de drift et usage sont partagés (Redis, PostgreSQL)", options: { bullet: true } },
  ], { isTextBox: true, x: 0.9, y: 3.6, w: 5.2, h: 2.6, fontSize: 15, color: C.text1, margin: 0, paraSpaceAfter: 8, valign: "top" });
  card(s, 6.7, 1.55, 6.0, 4.9, C.background2, "kubernetes");
  await iconCircle(s, "FaLayerGroup", 7.0, 1.8, 0.8, C.accent1);
  txt(s, "Kubernetes", { x: 8.0, y: 1.9, w: 4.4, h: 0.6, fontSize: 20, bold: true, valign: "middle" });
  // pods
  for (let i = 0; i < 10; i++) {
    const on = i < 4;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.0 + i * 0.53, y: 2.9, w: 0.43, h: 0.43, rectRadius: 0.06,
      fill: { color: on ? C.accent1 : C.background1 }, line: { color: C.accent1, width: 1 }, objectName: `pod-${i + 1}` });
  }
  txt(s, "HPA : 2 → 10 pods, cible 65 % CPU", { x: 7.0, y: 3.45, w: 5.4, h: 0.4, fontSize: 14, italic: true, color: C.text2 });
  s.addText([
    { text: "Readiness probe : aucun trafic tant que le modèle n'est pas chargé", options: { bullet: true, breakLine: true } },
    { text: "Rolling update sans indisponibilité, PodDisruptionBudget", options: { bullet: true, breakLine: true } },
    { text: "Ingress canary (canary-weight: 10)", options: { bullet: true, breakLine: true } },
    { text: "1 thread ONNX par pod : on scale en pods", options: { bullet: true } },
  ], { isTextBox: true, x: 7.0, y: 4.0, w: 5.4, h: 2.3, fontSize: 15, color: C.text1, margin: 0, paraSpaceAfter: 8, valign: "top" });
  s.addNotes("Ce qui rend le scaling possible : aucun état n'est gardé dans le processus de l'API. Sous Kubernetes, l'autoscaler se base sur le CPU, car l'inférence ONNX est limitée par le calcul. On fixe un seul thread par pod pour un comportement prévisible face à l'autoscaler.");

  // ================================================================ 12. Test de charge
  pres.addSection({ title: "Résultats" });
  s = content("Test de charge en production (Locust)", "Résultats");
  s.addChart(pres.charts.DOUGHNUT, [{ name: "Scénario", labels: ["Prédiction unitaire", "Lot de 8 images", "Consultation d'usage", "Sans clé (doit être 401)"], values: [85, 8, 5, 2] }], {
    x: 0.4, y: 1.45, w: 5.0, h: 4.6, holeSize: 55,
    chartColors: [HEX.accent1, HEX.accent3, HEX.accent2, HEX.accent5],
    showTitle: true, title: "Mix de requêtes simulé (%)", titleFontSize: 14, titleColor: HEX.dk1, titleFontFace: "+mn-lt",
    showLegend: true, legendPos: "b", legendFontSize: 12, legendFontFace: "+mn-lt", legendColor: HEX.dk1,
    showValue: true, showPercent: false, dataLabelColor: HEX.lt1, dataLabelFontSize: 12, dataLabelFontFace: "+mn-lt",
  });
  s.addTable([
    [head("Utilisateurs"), head("Débit (req/s)"), head("p50 (ms)"), head("p95 (ms)"), head("Erreurs")],
    ["10", r("à mesurer"), r("—"), r("—"), r("—")],
    ["50", "149", "14", "220", "0 %"],
    ["100", r("à mesurer"), r("—"), r("—"), r("—")],
    ["200", r("à mesurer"), r("—"), r("—"), r("—")],
  ], tableStyle(null, [1.45, 1.6, 1.25, 1.25, 1.25], 5.8, 1.6, { rowH: 0.55 }));
  txt(s, "Mesure à 50 utilisateurs : en local (Docker sur MacBook Air, 1 réplica stable + 1 canary, INT8), 2 513 requêtes, 0 échec. Canary : 213 / 2 130 prédictions = 10,0 % (cible 10 %).",
    { x: 5.8, y: 4.6, w: 6.8, h: 0.75, fontSize: 14, color: C.text2 });
  txt(s, "Expérience complémentaire : 100 utilisateurs avec 1, 2 puis 4 réplicas → gain du scaling horizontal",
    { x: 5.8, y: 5.4, w: 6.8, h: 0.7, fontSize: 14, italic: true, color: C.text1 });
  s.addNotes("Palier 50 utilisateurs mesuré en local : 149 req/s, médiane 14 ms, p95 220 ms, 0 % d'erreur ; la queue de latence vient de la contention CPU sur le portable. Compléter les autres paliers (sur la VM si possible). Montrer une capture Grafana prise pendant le test : répartition 90/10 et latence p95. Les 2 % de requêtes sans clé vérifient que la sécurité tient sous la charge : elles doivent toutes recevoir 401.");

  // ================================================================ 13. Validation drift
  s = content("Validation du détecteur de drift", "Résultats");
  s.addTable([
    [head("Perturbation"), head("Drift détecté"), head("Composantes rejetées"), head("PSI"), head("Confiance moy.")],
    ["Aucune (contrôle)", { text: "Limite (p 0,004)", options: { color: C.accent2, bold: true } }, "10 %", "0,014", "0,89"],
    ["Nuages", { text: "Oui (p ≈ 0)", options: { color: C.accent5, bold: true } }, "100 %", "8,69", "0,59"],
    ["Flou gaussien σ = 2", { text: "Oui (p ≈ 1e-265)", options: { color: C.accent5, bold: true } }, "100 %", "9,17", "0,73"],
    ["Bruit σ = 35", { text: "Oui (p ≈ 0)", options: { color: C.accent5, bold: true } }, "100 %", "14,15", { text: "0,96 (!)", options: { color: C.accent5, bold: true } }],
    ["Sous-exposition × 0,45", { text: "Oui (p ≈ 1e-77)", options: { color: C.accent5, bold: true } }, "100 %", "0,86", "0,74"],
    ["Sursaturation × 2,5", { text: "Oui (p ≈ 1e-40)", options: { color: C.accent5, bold: true } }, "90 %", "0,20", "0,82"],
  ], tableStyle(null, [3.4, 1.9, 2.4, 1.4, 1.9], 0.6, 1.6, { rowH: 0.55 }));
  await iconCircle(s, "FaExclamationTriangle", 0.6, 5.7, 0.7, C.accent2);
  txt(s, "Contrôle : faux positif limite (1 composante sur 10). La fenêtre ne contient que 300 images distinctes, équilibrées par classe : échantillons non indépendants et léger décalage réel. Le PSI reste stable (0,014) et l'alerte exige 5 min de drift persistant.",
    { x: 1.5, y: 5.6, w: 11.2, h: 0.95, fontSize: 14, color: C.text1, valign: "middle" });
  s.addNotes("Fenêtre de 1 000 requêtes, référence de 1 215 images de validation. Nuages : toutes les composantes rejetées, PSI de 8,7 et confiance passée de 0,89 à 0,59 : drift massif, comme attendu. Contrôle : une composante sur dix juste sous le seuil de Bonferroni (0,0041 contre 0,005). C'est un faux positif limite, expliqué par la réutilisation de 300 images (observations non indépendantes) et leur équilibrage par classe. Message clé : un test KS sur de grandes fenêtres est très sensible ; il faut combiner les signaux (PSI, confiance) et exiger une persistance avant de déclencher un ré-entraînement. Cas du bruit : la confiance MONTE à 0,96 alors que le PSI explose (14,1). Le modèle se trompe avec assurance en prédisant presque toujours la même classe. Surveiller la confiance seule n'aurait rien vu : c'est l'argument pour un détecteur sur les embeddings. Sursaturation : PSI de 0,20 seulement (sous le seuil usuel de 0,25), mais 9 composantes sur 10 rejetées : le test sur les embeddings repère des changements que la distribution des prédictions ne montre pas encore.");

  // ================================================================ 14. Démo
  s = content("Démonstration en direct", "Résultats");
  const demo = [
    ["FaPlay", "Système lancé", "docker compose ps · MLflow : v1 champion"],
    ["FaKey", "Sécurité", "curl sans clé → 401, avec clé → 200"],
    ["FaGlobeEurope", "Interface", "upload d'une image, probabilités, usage"],
    ["FaExchangeAlt", "Canary", "make train → v2 servie à 10 %, puis make promote"],
    ["FaExclamationTriangle", "Drift", "simulate_drift clouds → alerte dans Grafana"],
    ["FaTachometerAlt", "Charge", "Locust 50 utilisateurs + scale N=3 en direct"],
  ];
  for (let i = 0; i < demo.length; i++) {
    const [ic, t, d] = demo[i];
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.6 + col * 6.2, y = 1.55 + row * 1.7;
    card(s, x, y, 5.9, 1.45, C.background2, `demo-${i + 1}`);
    await iconCircle(s, ic, x + 0.3, y + 0.3, 0.85, i % 2 ? C.accent3 : C.accent1);
    txt(s, `${i + 1}. ${t}`, { x: x + 1.4, y: y + 0.25, w: 4.3, h: 0.45, fontSize: 17, bold: true });
    txt(s, d, { x: x + 1.4, y: y + 0.75, w: 4.3, h: 0.5, fontSize: 14, color: C.text2 });
  }
  s.addNotes("Préparer la démo à l'avance : système déjà lancé, v1 déjà entraînée, images d'exemple copiées (make sample-images), clés créées dans un fichier texte. L'entraînement de la v2 étant long, prévoir une v2 déjà enregistrée et ne montrer en direct que la promotion. Garder des captures d'écran en secours si le réseau ou la machine pose problème.");

  // ================================================================ 15. Limites
  pres.addSection({ title: "Conclusion" });
  s = content("Limites et perspectives", "Conclusion");
  const lim = [["Drift ≠ dégradation", "Pas d'étiquettes en production ; il faudrait une annotation d'échantillons"], ["Canary aléatoire", "Routage par requête et non par utilisateur ; promotion manuelle"], ["Sécurité réseau", "Pas de TLS ni de gestionnaire de secrets"], ["Disponibilité", "VM unique ; bases non managées"]];
  const per = [["Ré-entraînement automatique", "Déclenché par l'alerte de drift (Airflow / Prefect)"], ["Analyse canary automatique", "Promotion sur critères (Argo Rollouts, Flagger)"], ["13 bandes Sentinel-2", "Exploiter l'infrarouge (multispectral)"], ["Traitement de masse", "File de messages + workers pour des millions de tuiles"]];
  for (const [items, t, ic, col, x0] of [[lim, "Limites", "FaExclamationTriangle", C.accent5, 0.6], [per, "Perspectives", "FaRocket", C.accent1, 6.8]]) {
    await iconCircle(s, ic, x0, 1.5, 0.7, col);
    txt(s, t, { x: x0 + 0.9, y: 1.5, w: 4.5, h: 0.7, fontSize: 22, bold: true, valign: "middle", fontFace: THEME.headFontFace });
    items.forEach(([a, b], i) => {
      const y = 2.45 + i * 1.07;
      card(s, x0, y, 5.9, 0.92, C.background2, `${t}-${i + 1}`);
      txt(s, a, { x: x0 + 0.25, y: y + 0.08, w: 5.4, h: 0.38, fontSize: 15, bold: true });
      txt(s, b, { x: x0 + 0.25, y: y + 0.46, w: 5.4, h: 0.4, fontSize: 13, color: C.text2 });
    });
  }
  s.addNotes("Être honnêtes sur les limites : c'est souvent ce que le jury apprécie. Le plus important : notre détecteur signale un changement de distribution, pas une baisse de précision mesurée.");

  // ================================================================ 16. Fin
  s = pres.addSlide({ masterName: "TITRE_SOMBRE", sectionTitle: "Conclusion" });
  s.addText("Merci — des questions ?", { placeholder: "title" });
  s.addText([
    { text: "Un modèle, et tout le système qui le met en production :", options: { breakLine: true } },
    { text: "reproductible, sécurisé, observable, évolutif.", options: { breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 10 } },
    { text: "github.com/<owner>/eurosat-mlops", options: { color: C.accent2, fontFace: "Courier New", fontSize: 16 } },
  ], { placeholder: "body" });
  CLASSES.forEach((c, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const sz = 1.25, gap = 0.18;
    if (row > 3) return;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 8.75 + col * (sz + gap), y: 1.1 + row * (sz + gap) + (col === 1 ? 0.45 : 0), w: sz, h: sz,
      rectRadius: 0.1, fill: { color: c[2] }, line: { type: "none" }, objectName: `tuile-${c[0]}`,
    });
  });
  s.addNotes("Conclure sur le choix d'architecture principal : le découplage du code et du modèle par les alias du registre MLflow, qui permet de livrer, tester et annuler un modèle en quelques secondes.");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("écrit :", OUT);
})();
