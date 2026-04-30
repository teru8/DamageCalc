'use strict';
/**
 * @smogon/calc bridge – stdin/stdout line-delimited JSON.
 * Request:  { attacker, defender, move, field }
 * Response: { min, max }  (HP damage values)
 */
const { calculate, Pokemon, Move, Field } = require('@smogon/calc');
const readline = require('readline');

const GEN = 9;

const STATUS_MAP = {
  burn: 'brn', poison: 'psn', paralysis: 'par',
  sleep: 'slp', freeze: 'frz', toxic: 'tox',
  brn: 'brn', psn: 'psn', par: 'par', slp: 'slp', frz: 'frz', tox: 'tox',
};

const WEATHER_MAP = {
  sun: 'Sun', rain: 'Rain', sand: 'Sand', hail: 'Snow', snow: 'Snow',
};

const TERRAIN_MAP = {
  electric: 'Electric', grassy: 'Grassy', misty: 'Misty', psychic: 'Psychic',
};

// ── Extract min/max from result.damage ───────────────────────────────────
function extractDamage(result) {
  const dmg = result.damage;
  if (dmg === null || dmg === undefined) return { min: 0, max: 0 };
  if (typeof dmg === 'number') return { min: dmg, max: dmg };
  if (!Array.isArray(dmg) || dmg.length === 0) return { min: 0, max: 0 };

  // Multi-hit / Parental Bond: result.damage is an array of per-hit roll arrays
  if (Array.isArray(dmg[0])) {
    let min = 0, max = 0;
    for (const hit of dmg) {
      min += hit[0];
      max += hit[hit.length - 1];
    }
    return { min, max };
  }

  // Single hit: flat 16-element roll array
  return { min: dmg[0], max: dmg[dmg.length - 1] };
}

// ── Build Pokemon object from descriptor dict ─────────────────────────────
function buildPokemon(d) {
  const opts = {
    level: d.level || 50,
    nature: d.nature || 'Hardy',
    evs: d.evs || {},
    ivs: d.ivs !== undefined ? d.ivs : { hp: 31, atk: 31, def: 31, spa: 31, spd: 31, spe: 31 },
    boosts: d.boosts || {},
    status: STATUS_MAP[d.status || ''] || '',
  };
  if (d.ability)             opts.ability  = d.ability;
  if (d.item)                opts.item     = d.item;
  if (d.teraType)            opts.teraType = d.teraType;
  if (d.curHP !== undefined) opts.curHP    = d.curHP;
  if (d.gender)              opts.gender   = d.gender;
  if (d.alliesFainted !== undefined) opts.alliesFainted = d.alliesFainted;
  if (d.abilityOn !== undefined) opts.abilityOn = !!d.abilityOn;
  if (d.boostedStat) opts.boostedStat = d.boostedStat;
  return new Pokemon(GEN, d.species, opts);
}

// ── Handle a single calculation request ──────────────────────────────────
function handleCalc(req) {
  let atk, def, mv;

  try { atk = buildPokemon(req.attacker); }
  catch (e) { return { min: 0, max: 0, error: 'atk:' + e.message }; }

  try { def = buildPokemon(req.defender); }
  catch (e) { return { min: 0, max: 0, error: 'def:' + e.message }; }

  try {
    const mo = { isCrit: !!(req.move && req.move.isCrit) };
    if (req.move.hits > 1)      mo.hits      = req.move.hits;
    if (req.move.overrides)     mo.overrides  = req.move.overrides;
    mv = new Move(GEN, req.move.name, mo);
  } catch (e) { return { min: 0, max: 0, error: 'move:' + e.message }; }

  const f  = req.field || {};
  const fd = new Field({
    weather:    WEATHER_MAP[f.weather]  || undefined,
    terrain:    TERRAIN_MAP[f.terrain]  || undefined,
    isGravity: !!f.isGravity,
    isFairyAura: !!f.isFairyAura,
    isDarkAura:  !!f.isDarkAura,
    attackerSide: { isHelpingHand: !!f.helpingHand, isTailwind: !!f.tailwind },
    defenderSide: {
      isReflect: !!f.reflect,
      isLightScreen: !!f.lightScreen,
      isFriendGuard: !!f.friendGuard,
    },
  });

  let result;
  try { result = calculate(GEN, atk, def, mv, fd); }
  catch (e) { return { min: 0, max: 0, error: 'calc:' + e.message }; }

  return extractDamage(result);
}

// ── Main loop ─────────────────────────────────────────────────────────────
const rl = readline.createInterface({ input: process.stdin, terminal: false, crlfDelay: Infinity });

rl.on('line', (line) => {
  line = line.trim();
  if (!line) return;
  let res;
  try {
    res = handleCalc(JSON.parse(line));
  } catch (e) {
    res = { min: 0, max: 0, error: String(e) };
  }
  process.stdout.write(JSON.stringify(res) + '\n');
});
