/*
╔══════════════════════════════════════════════════════════════════════════════╗
║  REMNANT — Convolution Engine  (Lerdahl masking)                             ║
║  Launch AFTER remnant_sc.scd                                                 ║
║                                                                              ║
║  Tensione come mascheramento progressivo della sorgente (Lerdahl):          ║
║    0.0  → sorgente intatta   (dry = 1.0,  conv = 0.0,  scramble = 0)       ║
║    0.5  → ibrido timbrico    (dry = 0.5,  conv = 0.5,  scramble parziale)  ║
║    1.0  → sorgente distrutta (dry = 0.0,  conv = 1.0,  scramble pieno)     ║
║                                                                              ║
║  Pipeline per field:                                                         ║
║    SoundIn → [PitchScrambler] → [Convolution2] → [FreqShift+BPF] → Out     ║
║    dry attenuato da (1 - tension), non sommato al wet                        ║
║                                                                              ║
║  Evaluate in order:                                                          ║
║    Block 1 — IR params + generator + SynthDefs                               ║
║    Block 2 — UI                                                              ║
║    Block 3 — launch                                                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
*/


// ═══════════════════════════════════════════════════════════════════════════
// BLOCK 1 — Engine
// ═══════════════════════════════════════════════════════════════════════════
(
Routine({

// ── Categoria → comportamento del mascheramento ───────────────────────────
// Per ogni categoria Lerdahl:
//   irLen      — lunghezza IR in secondi
//   wetFloor   — wet minimo a tension=0 (solitamente 0, solo Stille >0)
//   pitchMax   — deviazione massima PitchShift a tension=1 (semitoni, come ratio)
//   pitchDisp  — dispersione pitch massima a tension=1
//   timeDisp   — dispersione temporale massima a tension=1
//   freqShift  — FreqShift massimo in Hz a tension=1
//   bpfQ       — Q del BPF a tension alta (basso Q = largo, alto Q = stretto/alieno)
//   irPitch    — frequenza fondamentale dell'IR
//   irMod      — rate di modulazione nell'IR
//   preDelayMs — pre-delay in ms

~conv_cats = ["Klang","Farbklang","Geräusch","Kadenz","Textur","Stille","Neutro"];

// [irLen, wetFloor, pitchMax, pitchDisp, timeDisp, freqShift, bpfQ, irPitch, irMod, preDelayMs]
~conv_params = Dictionary[
	// Klang: risonanze armoniche — deforma l'altezza ma mantiene struttura
	"Klang"     -> [4.0,  0.0,  1.15, 0.02, 0.02, 15.0,  0.3, 1.0,  0.1,  10],
	// Farbklang: colore spettrale — pitch scrambling medio, freqshift evidente
	"Farbklang" -> [3.0,  0.0,  1.35, 0.06, 0.04, 60.0,  0.5, 0.75, 0.3,   5],
	// Geräusch: rumore — scrambling massimo, IR rumoroso, freqshift ampio
	"Geräusch"  -> [2.0,  0.0,  1.8,  0.18, 0.12, 180.0, 1.2, 1.0,  0.5,   0],
	// Kadenz: impulsi — pre-delay percussivo, pitch stabile, BPF stretto
	"Kadenz"    -> [1.5,  0.0,  1.05, 0.01, 0.06, 8.0,   2.0, 1.0,  0.0,  30],
	// Textur: texture densa — modRate lento, freqshift minimo, IR lungo
	"Textur"    -> [6.0,  0.0,  1.25, 0.08, 0.08, 25.0,  0.2, 0.5,  0.05,  0],
	// Stille: quasi silenzio — IR impulsivo, tutti i processi minimi
	"Stille"    -> [0.1,  0.1,  1.0,  0.0,  0.0,  0.0,   0.1, 1.0,  0.0,   0],
	// Neutro: punto di partenza — trasformazione lieve ma presente
	"Neutro"    -> [1.0,  0.0,  1.08, 0.01, 0.01, 5.0,   0.3, 1.0,  0.0,   0],
];

~conv_sr     = s.sampleRate;
~conv_irBufs = Dictionary.new;

// ── IR generator ─────────────────────────────────────────────────────────────
// Gli IR definiscono il "colore" della categoria timbrica.
// Ogni categoria ha un profilo spettrale diverso che determina
// in che modo la sorgente viene trasformata a tensione alta.
~conv_genIR = { |cat|
	var p       = ~conv_params[cat];
	var irLen   = p[0];
	var irPitch = p[7];
	var irMod   = p[8];
	var sr      = ~conv_sr;
	var n       = (irLen * sr).round.asInteger.max(64);
	var sig     = Signal.newClear(n);
	var t, env, freq, peak;
	var ratios  = [1.0, 1.414, 1.732, 2.236, 2.618, 3.142, 4.0];

	switch(cat,

		// Klang: risonanze armoniche pure — l'IR amplifica le armoniche naturali
		"Klang", {
			freq = 120.0 * irPitch;
			n.do { |i|
				t      = i / sr;
				env    = exp(-3.0 * t / irLen);
				sig[i] = (
					sin(2pi * freq * t)       * env * 1.0  +
					sin(2pi * freq * 2.0 * t) * env * 0.5  +
					sin(2pi * freq * 3.0 * t) * env * 0.25 +
					sin(2pi * freq * 5.0 * t) * env * 0.12 +
					sin(2pi * freq * 7.0 * t) * env * 0.06
				) * 0.28;
			};
		},

		// Farbklang: intonazioneambigua — rapporti inarmonici, colore timbrico
		"Farbklang", {
			freq = 80.0 * irPitch;
			n.do { |i|
				t      = i / sr;
				env    = exp(-4.0 * t / irLen);
				sig[i] = ratios[0..4].sum({ |r, j|
					sin(2pi * freq * r * t + (j * 0.7)) * env / (j + 1)
				}) * 0.20;
			};
		},

		// Geräusch: rumore filtrato — distrugge la struttura spettrale
		"Geräusch", {
			n.do { |i|
				t      = i / sr;
				// doppio strato: rumore broadband + rumore filtrato in banda media
				env    = exp(-5.0 * t / irLen);
				sig[i] = (
					1.0.rand2 * env * 0.6 +
					(1.0.rand2 * sin(2pi * (600 + 2000.0.rand2) * t)) * env * 0.4
				) * 0.38;
			};
		},

		// Kadenz: impulsi periodici — enfatizza gli attacchi, cancella il sustain
		"Kadenz", {
			var spacing = (sr * 0.06).round.asInteger.max(1);
			var kDecay  = exp(-6.0 / irLen);
			var kAmp    = 1.0;
			n.do { |i|
				if((i % spacing) == 0) {
					sig[i] = kAmp;
					kAmp   = kAmp * kDecay;
				} {
					sig[i] = 0.0;
				};
			};
		},

		// Textur: modulazione FM lenta — crea un velo sonoro sopra la sorgente
		"Textur", {
			n.do { |i|
				t      = i / sr;
				env    = exp(-1.5 * t / irLen);
				// FM con carrier e modulator entrambi lenti
				sig[i] = sin(2pi * (
					200.0 * irPitch +
					80.0  * sin(2pi * irMod * t) +
					30.0  * sin(2pi * irMod * 2.7 * t)
				) * t) * env * 0.32;
			};
		},

		// Stille: quasi impulso — minima trasformazione, massima trasparenza
		"Stille", {
			sig[0] = 1.0;
			min(n, 32).do { |i|
				sig[i] = exp(-25.0 * i / 32.0) * 0.08;
			};
		},

		// Neutro: risonanza neutra con leggero rumore
		"Neutro", {
			freq = 400.0 * irPitch;
			n.do { |i|
				t      = i / sr;
				env    = exp(-4.0 * t / irLen);
				sig[i] = sin(2pi * freq * t) * env * 0.45 +
				         1.0.rand2 * env * 0.12;
			};
		},
	);

	peak = sig.abs.maxItem;
	if(peak > 0) { sig = sig / peak * 0.88 };
	sig
};

// ── Alloca IR buffers ─────────────────────────────────────────────────────────
~conv_cats.do { |cat|
	var sig = ~conv_genIR.(cat);
	~conv_irBufs[cat] = Buffer.loadCollection(s, sig);
};
s.sync;
"IR buffers ready".postln;


// ─────────────────────────────────────────────────────────────────────────────
// SynthDef \r_conv — pipeline completa di mascheramento Lerdahl
//
// tension 0.0 → dry puro, nessuna trasformazione
// tension 1.0 → sorgente completamente mascherata/irriconoscibile
//
// Pipeline:
//   1. PitchShift  — scramble melodico/timbrico (pitchRatio, pitchDisp, timeDisp)
//   2. Convolution2 — colore categoriale (IR specifico per categoria)
//   3. FreqShift   — rotazione spettrale (rompe le relazioni armoniche residue)
//   4. BPF         — finestra spettrale mobile (aliena la sorgente)
//
// Il dry viene MOLTIPLICATO per (1 - tension): a tension=1 è zero.
// Il wet viene scalato da tension: a tension=0 è zero.
// Non c'è "somma" dry+wet — c'è sostituzione progressiva.
// ─────────────────────────────────────────────────────────────────────────────
SynthDef(\r_conv, {
	|inBus=0, outBus=0,
	 tension=0.0,
	 irBuf=0,
	 pitchMax=1.15, pitchDisp=0.02, timeDisp=0.02,
	 freqShiftMax=15.0,
	 bpfQ=0.3,
	 preDelay=0,
	 amp=1.0|

	var dry, scrambled, convolved, shifted, filtered;
	var t, dryAmt, wetAmt;
	var bpfFreq;

	// tension con lag per evitare click ai cambi di gesto
	t = Lag.kr(tension.clip(0.0, 1.0), 0.5);

	// ── 1. Dry con pre-delay opzionale ────────────────────────────────────────
	dry = SoundIn.ar(inBus);
	dry = DelayN.ar(dry, 0.5, (preDelay / SampleRate.ir).max(0.0001));

	// ── 2. PitchShift (scrambling melodico) ──────────────────────────────────
	// pitchRatio: 1.0 a tension=0, pitchMax a tension=1
	// pitchDisp e timeDisp crescono linearmente con tension
	scrambled = PitchShift.ar(
		dry,
		windowSize:   0.1,
		pitchRatio:   1.0 + (t * (pitchMax - 1.0)),
		pitchDispersion: t * pitchDisp,
		timeDispersion:  t * timeDisp,
	);

	// ── 3. Convolution2 (colore categoriale) ─────────────────────────────────
	// Usa lo scrambled come input — l'IR si applica sul segnale già alterato
	convolved = Convolution2.ar(scrambled, irBuf, 0, 2048, 0.5);
	convolved = LeakDC.ar(convolved);

	// ── 4. FreqShift (rotazione spettrale) ───────────────────────────────────
	// A tension alta: sposta le frequenze di freqShiftMax Hz
	// Rompe definitivamente le relazioni armoniche residue dopo la conv
	shifted = FreqShift.ar(convolved, t * freqShiftMax);

	// ── 5. BPF mobile (finestra spettrale aliena) ─────────────────────────────
	// A tension bassa: BPF largo e centrato su frequenze naturali (~1kHz)
	// A tension alta: BPF sempre più stretto e centro sempre più insolito
	bpfFreq = LinExp.kr(t, 0.0, 1.0, 800.0, 3200.0);
	filtered = BPF.ar(shifted, bpfFreq, 1.0 / (0.1 + (t * bpfQ)));

	// ── Mix: sostituzione progressiva (non somma) ─────────────────────────────
	// dryAmt: 1.0 → 0.0 (curva logaritmica — il dry sparisce rapidamente)
	// wetAmt: 0.0 → 1.0 (curva esponenziale — il wet arriva gradualmente)
	dryAmt = (1.0 - t).pow(1.5);
	wetAmt = t.pow(0.7);

	Out.ar(outBus,
		Limiter.ar(
			((dry * dryAmt) + (filtered * wetAmt)) * amp,
			0.92
		) ! 2
	);
}).add;

s.sync;


// ── Mappa categoria → SynthDef ────────────────────────────────────────────────
~r_catSynth = Dictionary.new;
~conv_cats.do { |cat| ~r_catSynth[cat] = \r_conv };
~r_catSynth["Gerausch"] = \r_conv;  // alias senza umlaut


// ── Override ~r_gesture ───────────────────────────────────────────────────────
// Sostituisce la versione in remnant_sc.scd.
// Legge i parametri di mascheramento dalla categoria Lerdahl corrente
// e li passa al SynthDef \r_conv per ogni field.
~r_gesture = { |category, tension, azimuth|
	var cat, irBuf, params, pitchMax, pitchDisp, timeDisp, freqShMax, bpfQ, preDelay, finalT;
	var dispC, dispCol;
	cat      = category ?? "Neutro";
	irBuf    = ~conv_irBufs[cat] ?? ~conv_irBufs["Neutro"];
	params   = ~conv_params[cat]  ?? ~conv_params["Neutro"];
	pitchMax   = params[2];
	pitchDisp  = params[3];
	timeDisp   = params[4];
	freqShMax  = params[5];
	bpfQ       = params[6];
	preDelay   = (params[9] / 1000.0 * ~conv_sr).round.asInteger;
	finalT = (tension + (~r_flucoTension * 0.4)).clip(0, 1);
	dispC = Dictionary[
		"Klang"     -> Color(0.29, 0.56, 0.85),
		"Farbklang" -> Color(0.36, 0.72, 0.36),
		"Geräusch"  -> Color(0.87, 0.36, 0.36),
		"Kadenz"    -> Color(0.73, 0.46, 0.09),
		"Textur"    -> Color(0.61, 0.35, 0.71),
		"Stille"    -> Color(0.6,  0.6,  0.6 ),
		"Neutro"    -> Color(0.5,  0.5,  0.5 ),
	];
	dispCol = dispC[cat] ?? Color(0.5, 0.5, 0.5);

	~r_gestTension = tension ?? 0.3;
	~r_currentCat  = cat;
	~r_currentAz   = azimuth ?? 180.0;
	if(~conv_catDisplay.notNil) {
		{ ~conv_catDisplay.string_(cat).stringColor_(dispCol) }.defer;
	};
	if(~r_hudCatDisplay.notNil) {
		{ ~r_hudCatDisplay.string_(cat).stringColor_(dispCol) }.defer;
	};

	~r_nFields.do { |i|
		var adcBus  = ~r_fieldChs[i];
		var fieldAz = ~r_fieldAz[i];
		var entry   = ~r_synths[i];

		if(entry.notNil) {
			var procA  = entry[0];
			var xfader = entry[1];
			var spat   = entry[2];

			// Nuovo synth con parametri completi di mascheramento
			var procB = Synth(\r_conv, [
				\inBus,       adcBus,
				\outBus,      ~r_procBusB[i].index,
				\tension,     finalT,
				\irBuf,       irBuf.bufnum,
				\pitchMax,    pitchMax,
				\pitchDisp,   pitchDisp,
				\timeDisp,    timeDisp,
				\freqShiftMax, freqShMax,
				\bpfQ,        bpfQ,
				\preDelay,    preDelay,
				\amp,         ~r_masterVol,
			], target: ~r_gProc);

			xfader.set(\busA, ~r_procBusA[i].index,
			           \busB, ~r_procBusB[i].index);
			spat.set(\azimuth, fieldAz);

			// Crossfade verso nuovo synth
			Routine({
				var steps = 40;
				var dt    = ~r_xfadeTime / steps;
				steps.do { |i2|
					xfader.set(\xfade, (i2 + 1) / steps);
					dt.wait;
				};
				try { procA.free };
				~r_synths[i] = [procB, xfader, spat];
				xfader.set(
					\busA,  ~r_procBusB[i].index,
					\busB,  ~r_procBusA[i].index,
					\xfade, 0.0
				);
			}).play(AppClock);
		};
	};

	("▶ Conv [" ++ cat ++ "] t=" ++ finalT.round(0.01)
	 ++ " pitch=" ++ pitchMax
	 ++ " fShift=" ++ freqShMax
	 ++ "Hz bpfQ=" ++ bpfQ).postln;
};

// ── Update live di tension senza cambiare categoria ───────────────────────────
// Chiamabile dall'HUD per aggiornare solo la tension in tempo reale
// senza rigenerare il synth (usa .set su procA).
~r_setTension = { |tension|
	var finalT = (tension + (~r_flucoTension * 0.4)).clip(0, 1);
	~r_nFields.do { |i|
		var entry;
		entry = ~r_synths[i];
		if(entry.notNil) {
			entry[0].set(\tension, finalT);
		};
	};
};

// Trigger iniziale
AppClock.sched(0.1, {
	~r_gesture.("Neutro", 0.0, 180);
	nil;
});

// ── IR regen (con aggiornamento live se categoria attiva) ─────────────────────
~conv_regenIR = { |cat|
	var sig, oldBuf, newBuf;
	sig    = ~conv_genIR.(cat);
	oldBuf = ~conv_irBufs[cat];
	newBuf = Buffer.loadCollection(s, sig);
	Routine({
		s.sync;
		~conv_irBufs[cat] = newBuf;
		oldBuf.free;
		("IR regen: " ++ cat).postln;
		if(~r_currentCat == cat) {
			~r_gesture.(cat, ~r_gestTension, ~r_currentAz);
		};
	}).play(AppClock);
};

// ── Riferimento globale al display categoria (aggiornato da ~r_gesture) ─────
~conv_catDisplay = nil;
~r_hudCatDisplay = nil;

"═══════════════════════════════════════════════════════════════".postln;
"Conv engine (Lerdahl masking) ready".postln;
"  tension 0.0 → sorgente intatta".postln;
"  tension 1.0 → sorgente irriconoscibile".postln;
"  ~r_setTension.(0.8) — aggiorna solo tension (no synth rebuild)".postln;
"  ~r_gesture.(\"Geräusch\", 1.0, 90) — cambio categoria + tension".postln;
"═══════════════════════════════════════════════════════════════".postln;

}).play(AppClock);
)


// ═══════════════════════════════════════════════════════════════════════════
// BLOCK 2 — UI
// ═══════════════════════════════════════════════════════════════════════════
(
~conv_buildUI = {
	var win, layout, bgCol, accentCol, dimCol, selCol, warnCol, monoS, monoSB;
	var currentCat, catBtns, paramDefs, sliders, valDisplays;
	var tensionRow, tensionSlider, tensionDisp, catGrid;
	var catDisplay, tensionLive;

	win        = Window("CONV · Lerdahl", Rect(290, 20, 260, 420), resizable: false)
	             .background_(Color(0.07, 0.07, 0.07, 0.95))
	             .alwaysOnTop_(true);
	layout     = VLayout();
	bgCol      = Color(0.07, 0.07, 0.07);
	accentCol  = Color(0.22, 0.55, 0.9);
	dimCol     = Color(0.4,  0.4,  0.4);
	selCol     = Color(0.9,  0.5,  0.1);
	warnCol    = Color(0.9,  0.2,  0.2);
	monoS      = Font("Courier New", 9);
	monoSB     = Font("Courier New", 9, bold: true);
	currentCat = "Neutro";
	catBtns    = Dictionary.new;
	sliders     = Dictionary.new;
	valDisplays = Dictionary.new;
	tensionRow  = HLayout();
	tensionSlider = Slider();
	tensionDisp = StaticText();
	catGrid     = HLayout();

	// Parametri esposti nell'UI — subset di ~conv_params per categoria
	// [key, label, min, max, step, isExp, paramIdx]
	paramDefs = [
		[\irLen,      "IR len (s)",      0.05, 8.0,  0.05, true,  0],
		[\pitchMax,   "pitch max",       1.0,  2.5,  0.01, false, 2],
		[\pitchDisp,  "pitch disp",      0.0,  0.3,  0.01, false, 3],
		[\timeDisp,   "time disp",       0.0,  0.3,  0.01, false, 4],
		[\freqShift,  "freq shift (Hz)", 0.0,  400.0,1.0,  false, 5],
		[\bpfQ,       "BPF Q",           0.0,  3.0,  0.01, false, 6],
		[\preDelay,   "pre-delay (ms)",  0,    100,  1,    false, 9],
	];

	win.layout = layout;
	layout.margins  = [10, 10, 10, 10];
	layout.spacing  = 4;

	// ── Header ──────────────────────────────────────────────────────────────
	layout.add(
		StaticText()
		.string_("C O N V  ·  L E R D A H L")
		.font_(Font("Georgia", 10, italic: true))
		.stringColor_(dimCol)
		.align_(\center)
	);
	layout.add(
		StaticText()
		.string_("tension 0 → dry  ·  tension 1 → irriconoscibile")
		.font_(Font("Courier New", 8))
		.stringColor_(Color(0.3, 0.3, 0.3))
		.align_(\center)
	);

	// ── Categoria attiva (aggiornata da ~r_gesture) ─────────────────────────
	catDisplay = StaticText()
		.string_("— in attesa —")
		.font_(Font("Georgia", 13, italic: true))
		.stringColor_(Color(0.5, 0.5, 0.5))
		.align_(\center);
	~conv_catDisplay = catDisplay;
	layout.add(catDisplay);

	// ── Tension monitor (live) ───────────────────────────────────────────────
	tensionRow.margins = [0,0,0,0];
	tensionRow.spacing = 6;
	tensionSlider
		.orientation_(\horizontal)
		.background_(Color(0.12, 0.12, 0.12))
		.knobColor_(warnCol)
		.value_(0.0);
	tensionDisp
		.string_("0.00")
		.font_(monoSB)
		.stringColor_(warnCol)
		.fixedWidth_(34)
		.align_(\right);
	tensionSlider.action = { |sl|
		var t = sl.value;
		tensionDisp.string_(t.round(0.01).asString);
		~r_setTension.(t);
	};
	tensionRow.add(StaticText()
		.string_("tension")
		.font_(monoS).stringColor_(dimCol).fixedWidth_(60));
	tensionRow.add(tensionSlider);
	tensionRow.add(tensionDisp);
	layout.add(tensionRow);

	// ── Separatore ──────────────────────────────────────────────────────────
	layout.add(StaticText()
		.string_("────────────────────────────")
		.stringColor_(dimCol).font_(monoS).align_(\center));

	// ── Bottoni categoria ────────────────────────────────────────────────────
	layout.add(StaticText()
		.string_("categoria IR")
		.font_(monoS).stringColor_(dimCol).align_(\left));

	catGrid.spacing = 2;
	catGrid.margins = [0,0,0,0];

	~conv_cats.do { |cat|
		var short = cat.copyRange(0, min(3, cat.size - 1));
		var btn = Button()
			.states_([
				[short, dimCol, Color(0.15, 0.15, 0.15)],
				[short, bgCol,  selCol],
			])
			.font_(monoSB);

		btn.action = { |b|
			var p, btnC, btnCol;
			if(b.value == 1) {
				p = ~conv_params[cat];
				catBtns.do { |ob| if(ob !== btn) { ob.value_(0) } };
				currentCat = cat;
				// Aggiorna display categoria attiva
				btnC = Dictionary[
					"Klang"     -> Color(0.29, 0.56, 0.85),
					"Farbklang" -> Color(0.36, 0.72, 0.36),
					"Geräusch"  -> Color(0.87, 0.36, 0.36),
					"Kadenz"    -> Color(0.73, 0.46, 0.09),
					"Textur"    -> Color(0.61, 0.35, 0.71),
					"Stille"    -> Color(0.6,  0.6,  0.6 ),
					"Neutro"    -> Color(0.5,  0.5,  0.5 ),
				];
				btnCol = btnC[cat] ?? Color(0.5, 0.5, 0.5);
				if(~conv_catDisplay.notNil) {
					{ ~conv_catDisplay.string_(cat).stringColor_(btnCol) }.defer;
				};
				if(~r_hudCatDisplay.notNil) {
					{ ~r_hudCatDisplay.string_(cat).stringColor_(btnCol) }.defer;
				};
				// Aggiorna slider ai valori della categoria selezionata
				paramDefs.do { |pd|
					var key    = pd[0];
					var mn     = pd[2];
					var mx     = pd[3];
					var isExp  = pd[5];
					var pIdx   = pd[6];
					var val    = p[pIdx];
					var norm   = if(isExp) {
						(log(val.max(0.0001)) - log(mn)) / (log(mx) - log(mn))
					} {
						(val - mn) / (mx - mn)
					};
					sliders[key].value_(norm.clip(0,1));
					valDisplays[key].string_(val.round(0.01).asString);
				};
			};
		};
		catBtns[cat] = btn;
		catGrid.add(btn);
	};
	layout.add(catGrid);

	layout.add(StaticText()
		.string_("────────────────────────────")
		.stringColor_(dimCol).font_(monoS).align_(\center));

	// ── Sliders parametri ────────────────────────────────────────────────────
	paramDefs.do { |pd|
		var key    = pd[0];
		var label  = pd[1];
		var mn     = pd[2];
		var mx     = pd[3];
		var step   = pd[4];
		var isExp  = pd[5];
		var pIdx   = pd[6];
		var row    = HLayout();
		var lbl    = StaticText()
		             .string_(label).font_(monoS)
		             .stringColor_(dimCol).fixedWidth_(100);
		var valD   = StaticText()
		             .string_("—").font_(monoS)
		             .stringColor_(accentCol).fixedWidth_(38).align_(\right);
		var sl     = Slider()
		             .orientation_(\horizontal)
		             .background_(Color(0.12,0.12,0.12))
		             .knobColor_(accentCol);

		sl.action = {
			var norm = sl.value;
			var p    = ~conv_params[currentCat].copy;
			var val  = if(isExp) {
				exp(log(mn) + norm * (log(mx) - log(mn)))
			} {
				mn + norm * (mx - mn)
			}.round(step);
			p[pIdx]  = val;
			valD.string_(val.asString);
			~conv_params[currentCat] = p;
		};

		row.margins = [0,0,0,0]; row.spacing = 4;
		row.add(lbl); row.add(sl); row.add(valD);
		layout.add(row);
		sliders[key]     = sl;
		valDisplays[key] = valD;
	};

	layout.add(StaticText()
		.string_("────────────────────────────")
		.stringColor_(dimCol).font_(monoS).align_(\center));

	// ── Bottoni azione ───────────────────────────────────────────────────────
	layout.add(Button()
		.states_([["APPLY + REGEN IR", Color.white, Color(0.08,0.25,0.08)]])
		.font_(monoSB)
		.action_({ ~conv_regenIR.(currentCat) })
	);

	layout.add(Button()
		.states_([["TEST MASKING (t=1.0)", Color.white, Color(0.35,0.08,0.08)]])
		.font_(monoSB)
		.action_({
			~r_gesture.(currentCat, 1.0, ~r_currentAz ?? 180);
			tensionSlider.value_(1.0);
			tensionDisp.string_("1.00");
		})
	);

	layout.add(Button()
		.states_([["RESET (t=0.0)", dimCol, Color(0.15,0.15,0.15)]])
		.font_(monoSB)
		.action_({
			~r_setTension.(0.0);
			tensionSlider.value_(0.0);
			tensionDisp.string_("0.00");
		})
	);

	// ── Init slider a Neutro ─────────────────────────────────────────────────
	{
		var p = ~conv_params["Neutro"];
		catBtns["Neutro"].value_(1);
		paramDefs.do { |pd|
			var key   = pd[0];
			var mn    = pd[2];
			var mx    = pd[3];
			var isExp = pd[5];
			var pIdx  = pd[6];
			var val   = p[pIdx];
			var norm  = if(isExp) {
				(log(val.max(0.0001)) - log(mn)) / (log(mx) - log(mn))
			} {
				(val - mn) / (mx - mn)
			};
			sliders[key].value_(norm.clip(0,1));
			valDisplays[key].string_(val.round(0.01).asString);
		};
	}.defer(0.1);

	win.front;
};
"~conv_buildUI defined — evaluate Block 3 to open".postln;
)


// ═══════════════════════════════════════════════════════════════════════════
// BLOCK 3 — Launch UI
// ═══════════════════════════════════════════════════════════════════════════
(
~conv_buildUI.();
"Convolution interface open.".postln;
"".postln;
"Quick test:".postln;
"  ~r_gesture.(\"Geräusch\", 1.0, 90)  — mascheramento massimo".postln;
"  ~r_gesture.(\"Klang\",    0.3, 0)   — colore armonico lieve".postln;
"  ~r_setTension.(0.75)               — solo tension, no synth rebuild".postln;
)
