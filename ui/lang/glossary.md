# Glossary for Clavitone's translations

One word for each idea in each language, so the interface and the help agree.
The interface is English in the source (nui/, wrapped in T()). Each table,
ui/lang/<code>.json, maps each English text to its translation. The help's
texts are in ui/lang/help_<code>.json. Check the tables with
examples/i18n_strings.py and build the help with examples/help_json.py.

**Every translation here is drafted, not reviewed.** A native reader of each
language should check it before it ships.

## Rules for every language

- **Keep these as they are:**
  - names: GS, GM, GM2, MIDI, MPE, MT-32, CM-64, SC-55, SC-88, SC-88Pro, SC-8850, CVT1, Clavitone, the Messenger, Sound Canvas;
  - patch, instrument and drum names (they come from data);
  - temperament names (Werckmeister III, Kirnberger, Vallotti);
  - organ stop names (Principal 8', Mixtur, Gedackt);
  - units (Hz, ms, dB, %, cents, BPM);
  - note names (C4, A4 = 440 Hz).
- **Placeholders:** keep every `{0}`, `{1}` and every printf specifier (`%d`, `%s`, `%.1f`, `%%`).
  - `{n}` may move to where the language puts it.
  - `%` ones must stay in the same order.
- **Capitals:** a text the English writes in capitals is a label or heading. Write it in capitals too, with the accents capitalised (É, À, Ñ, Ü), except Japanese, which has no case.
  - German keeps ß in lower case; in capitals it becomes SS (STRASSE).
- **Length:** labels sit in fixed boxes. Keep each label about as long as the English, at most a third longer.
  - Use the shortest clear word, and a standard abbreviation where the language has one (German Lautst. for Lautstärke).
  - Sentences (help and notes) may run longer; they wrap.
- **Register:**
  - German: "du" or the imperative, as music software does.
  - French: the imperative, "vous" where a pronoun is needed.
  - Spanish: "tú" or the imperative.
  - Japanese: です/ます in sentences, plain nouns for labels.
- **Tone:** the English is plain and concrete ("the part's patch", "turn it up"). Keep that; don't make it formal or flowery.

## Terms

| English | 日本語 | Deutsch | Français | Español |
|---|---|---|---|---|
| part (one of 16+ instrument slots) | パート | Part | partie | parte |
| patch (a part's sound) | 音色 | Klang | son | sonido |
| program (GM number) | プログラム | Programm | programme | programa |
| variation (GS bank) | バリエーション | Variation | variation | variación |
| preset | プリセット | Preset | préréglage | preajuste |
| scene | シーン | Szene | scène | escena |
| card (a screen of the interface) | カード | Karte | carte | tarjeta |
| channel | チャンネル | Kanal | canal | canal |
| drum set / kit | ドラムセット | Drumset | kit de batterie | kit de batería |
| key (piano key) | 鍵盤 | Taste | touche | tecla |
| note | ノート | Note | note | nota |
| velocity | ベロシティ | Anschlagstärke (Velocity) | vélocité | velocidad |
| level | レベル | Pegel | niveau | nivel |
| volume | 音量 | Lautstärke | volume | volumen |
| pan | パン | Panorama | panoramique | panorama |
| reverb | リバーブ | Hall | réverbération (réverb) | reverberación (reverb) |
| chorus | コーラス | Chorus | chorus | chorus |
| delay | ディレイ | Delay | délai | delay |
| effect / insertion effect | エフェクト / インサーション | Effekt / Insert-Effekt | effet / effet d'insertion | efecto / efecto de inserción |
| room (the space the sound is in) | ルーム | Raum | salle | sala |
| tuning / temperament | チューニング / 音律 | Stimmung | accordage / tempérament | afinación / temperamento |
| stop (organ) | ストップ | Register | jeu | registro |
| drawbar | ドローバー | Zugriegel | tirette | tirador (drawbar) |
| pedal (sustain …) | ペダル | Pedal | pédale | pedal |
| damper | ダンパー | Dämpfer | étouffoir | apagador |
| amp / amplifier | アンプ | Verstärker | ampli | amplificador |
| pickup | ピックアップ | Tonabnehmer | micro | pastilla |
| speaker / cabinet | スピーカー | Lautsprecher | haut-parleur | altavoz |
| valve (tube) | 真空管 | Röhre | lampe | válvula |
| rotary (Leslie-type) | ロータリー | Rotor | cabine rotative | rotativo |
| wheel (mod wheel) | ホイール | Rad | molette | rueda |
| bend (pitch bend) | ベンド | Bend | pitch-bend | bend |
| aftertouch | アフタータッチ | Aftertouch | aftertouch | aftertouch |
| controller / control | コントローラー | Controller | contrôleur | controlador |
| route (a rewrite of a control) | ルート | Route | routage | ruta |
| matrix (controller matrix) | マトリクス | Matrix | matrice | matriz |
| synth | シンセ | Synth | synthé | sintetizador |
| oscillator | オシレーター | Oszillator | oscillateur | oscilador |
| filter / cutoff / resonance | フィルター / カットオフ / レゾナンス | Filter / Cutoff / Resonanz | filtre / coupure / résonance | filtro / corte / resonancia |
| envelope (attack, decay, sustain, release) | エンベロープ（アタック、ディケイ、サステイン、リリース） | Hüllkurve (Attack, Decay, Sustain, Release) | enveloppe (attaque, déclin, maintien, relâchement) | envolvente (ataque, caída, sostenido, liberación) |
| LFO | LFO | LFO | LFO | LFO |
| file (MIDI file) | ファイル | Datei | fichier | archivo |
| render (to audio) | 書き出し | rendern / Export | rendu | renderizar / exportar |
| render as heard | 聞こえたまま書き出し | wie gehört rendern | rendu tel qu'entendu | renderizar tal como suena |
| best quality | 最高品質 | Beste Qualität | meilleure qualité | máxima calidad |
| play live | ライブ再生 | live spielen | jouer en direct | tocar en vivo |
| library | ライブラリ | Bibliothek | bibliothèque | biblioteca |
| standard (GM, GS …) | 規格 | Standard | norme | estándar |
| setup | 設定 | Setup | configuration | configuración |
| borrowed time (rubato) | 借りた時間 | geliehene Zeit | temps emprunté | tiempo prestado |
| underrun / dropout | 音切れ | Aussetzer | décrochage | corte |
| help | ヘルプ | Hilfe | aide | ayuda |
| quit | 終了 | Beenden | quitter | salir |
| mute / solo | ミュート / ソロ | Stumm / Solo | muet / solo | silencio / solo |
| panic (all notes off) | パニック | Panik | panique | pánico |
