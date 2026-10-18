// Порт legacy/calculator.py — калькулятор базовых ресурсов заводского заказа.
//
// Высокоуровневые материалы раскладываются на первоуровневые:
//   м4 -> обр. ×1;  р.сплав -> обр. ×5 + редкие ×20 + кокс ×60
//   сталь -> обр. ×3 + кокс ×125 + топливо ×1 (батчами по 3)
//   м5 -> м1 ×10 + м2 ×10 + обр. ×9 + кокс ×(245+375) + топливо ×3
// Рецепты: кокс с серой (200 угля = 165 кокса + 15 серы) / без (= 180 кокса);
// топливо из угля (100) или серы (60); обр. через металлолом в доле scrapRatio.
import { pyRound } from "./py";

export type CokeRecipe = "with_sulfur" | "no_sulfur";
export type FuelRecipe = "sulfur" | "coal";

export interface BaseCost {
  coal: number;
  scrap: number;
  components: number;
  sulfur: number;
  rare_mats: number;
  sulfur_byproduct: number;
}

export function baseCost(p: Partial<BaseCost> = {}): BaseCost {
  return { coal: 0, scrap: 0, components: 0, sulfur: 0, rare_mats: 0, sulfur_byproduct: 0, ...p };
}

export function addCost(a: BaseCost, b: BaseCost): BaseCost {
  return {
    coal: a.coal + b.coal,
    scrap: a.scrap + b.scrap,
    components: a.components + b.components,
    sulfur: a.sulfur + b.sulfur,
    rare_mats: a.rare_mats + b.rare_mats,
    sulfur_byproduct: a.sulfur_byproduct + b.sulfur_byproduct,
  };
}

/** Сера к покупке с учётом побочки от кокса. */
export function netSulfur(c: BaseCost): number {
  return Math.max(0, c.sulfur - c.sulfur_byproduct);
}

export interface FirstLevelMats {
  m1: number;
  m2: number;
  m3: number;
  proc: number;
  build: number;
  fuel: number;
  rare: number;
  coke: number;
}

export const RECIPE_KEYS = ["steel", "m1", "m2", "m3", "m4", "m5", "proc", "rare", "build"] as const;
export type Recipe = Partial<Record<(typeof RECIPE_KEYS)[number], number>>;

function toInt(x: unknown): number {
  const n = Number(x ?? 0);
  return Number.isFinite(n) ? Math.trunc(n) : 0;
}

export function expandToFirstLevel(costs: Recipe): FirstLevelMats {
  const s = Object.fromEntries(RECIPE_KEYS.map((k) => [k, toInt(costs[k])])) as Record<
    (typeof RECIPE_KEYS)[number],
    number
  >;
  const fl: FirstLevelMats = { m1: 0, m2: 0, m3: 0, proc: 0, build: 0, fuel: 0, rare: 0, coke: 0 };

  fl.m1 += s.m5 * 10;
  fl.m2 += s.m5 * 10;
  fl.proc += s.m5 * 9;
  fl.coke += s.m5 * (245 + 375);
  fl.fuel += s.m5 * 3;

  if (s.steel > 0) {
    const batches = Math.ceil(s.steel / 3);
    fl.proc += batches * 9;
    fl.coke += batches * 375;
    fl.fuel += batches * 3;
  }

  fl.proc += s.rare * 5;
  fl.rare += s.rare * 20;
  fl.coke += s.rare * 60;

  fl.proc += s.m4;

  fl.m1 += s.m1;
  fl.m2 += s.m2;
  fl.m3 += s.m3;
  fl.proc += s.proc;
  fl.build += s.build;
  return fl;
}

function coalForCoke(cokeNeeded: number, cokeRecipe: string): BaseCost {
  if (cokeNeeded <= 0) return baseCost();
  const perBatch = cokeRecipe === "with_sulfur" ? 165 : 180;
  const batches = Math.ceil(cokeNeeded / perBatch);
  return baseCost({
    coal: batches * 200,
    sulfur_byproduct: cokeRecipe === "with_sulfur" ? batches * 15 : 0,
  });
}

function costM1(count: number, cokeRecipe: string): BaseCost {
  const ck = coalForCoke(count * 75, cokeRecipe);
  return baseCost({ coal: ck.coal, scrap: count * 15, sulfur_byproduct: ck.sulfur_byproduct });
}

const costM2 = (count: number) => baseCost({ scrap: count * 15 });
const costM3 = (count: number) => baseCost({ sulfur: count * 20, scrap: count * 15 });

function costProc(count: number, scrapRatio: number): BaseCost {
  const viaScrap = pyRound(count * scrapRatio);
  const viaComp = count - viaScrap;
  return baseCost({ scrap: viaScrap * 95 + viaComp * 5, components: pyRound(viaComp * (55 / 3)) });
}

const costBuild = (count: number) => baseCost({ scrap: count * 5 });

function costFuel(count: number, fuelRecipe: string): BaseCost {
  return fuelRecipe === "sulfur" ? baseCost({ sulfur: count * 60 }) : baseCost({ coal: count * 100 });
}

const costRare = (count: number) => baseCost({ rare_mats: count });

export interface MatDetail {
  matKey: string;
  count: number;
  cost: BaseCost;
}

export function calculateDetail(
  costs: Recipe,
  cokeRecipe: string = "with_sulfur",
  fuelRecipe: string = "coal",
  scrapRatio = 0,
): MatDetail[] {
  const fl = expandToFirstLevel(costs);
  const out: MatDetail[] = [];
  const push = (key: keyof FirstLevelMats, cost: BaseCost) =>
    out.push({ matKey: key, count: fl[key], cost });
  if (fl.m1 > 0) push("m1", costM1(fl.m1, cokeRecipe));
  if (fl.m2 > 0) push("m2", costM2(fl.m2));
  if (fl.m3 > 0) push("m3", costM3(fl.m3));
  if (fl.proc > 0) push("proc", costProc(fl.proc, scrapRatio));
  if (fl.build > 0) push("build", costBuild(fl.build));
  if (fl.fuel > 0) push("fuel", costFuel(fl.fuel, fuelRecipe));
  if (fl.rare > 0) push("rare", costRare(fl.rare));
  if (fl.coke > 0) push("coke", coalForCoke(fl.coke, cokeRecipe));
  return out;
}

export function totalCost(
  costs: Recipe,
  cokeRecipe: string = "with_sulfur",
  fuelRecipe: string = "coal",
  scrapRatio = 0,
): BaseCost {
  return calculateDetail(costs, cokeRecipe, fuelRecipe, scrapRatio).reduce(
    (acc, d) => addCost(acc, d.cost),
    baseCost(),
  );
}
