import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {weeklyMetrics} from "../components/weeklyMetrics.ts";
test("duration-weighted energy and availability exclude terminal epoch",()=>{
 const study={timestamps:["2026-10-01T00:00:00Z","2026-10-01T01:00:00Z","2026-10-01T03:00:00Z"],
 scenarios:[{id:"a",rows:[[100,0,0,0,0,false,false,true],[0,0,0,0,0,false,false,false],[9999,0,0,0,0,false,false,true]]}]};
 const m=weeklyMetrics(study,"a");
 assert.equal(m.kwh,.1); assert.equal(m.hours,3); assert.equal(m.commsHours,1);
 assert.ok(Math.abs(m.poweredPercent-100/3)<1e-10); assert.equal(weeklyMetrics(study,"missing"),null);
 study.timestamps[1]=study.timestamps[0]; assert.equal(weeklyMetrics(study,"a"),null);
});
test("all five real studies cover 168 hours with bounded availability",()=>{
 for(const id of ["test-site-a","connecting-ridge","haworth","malapert-massif","nobile-rim-1"]){
 const study=JSON.parse(readFileSync(new URL(`../../../outputs/spacecraft/${id}.json`,import.meta.url)));
 for(const scenario of study.scenarios){const m=weeklyMetrics(study,scenario.id);
 assert.ok(m); assert.ok(Math.abs(m.hours-168)<1e-8); assert.ok(m.kwh>=0);
 assert.ok(m.commsPercent>=0&&m.commsPercent<=100);assert.ok(m.poweredPercent>=0&&m.poweredPercent<=100);}
 }
});
