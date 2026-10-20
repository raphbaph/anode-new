(function(root){
const defaults={direct:5,fintech:15,rsr:800,price:0.004,yield:4.5,fixed:20,target:15,hurdle:6,trigger:20,maxShare:30};
function calculate(s,rule){
 const total=s.direct+s.fintech,capital=s.rsr*s.price,oc=total?capital/total*100:0;
 const fintechStaker=rule==='responsive'?0.1+(s.maxShare/100-0.1)*Math.max(0,Math.min(1,(s.trigger-oc)/Math.max(.01,s.trigger-s.target))):.1;
 const revenue=total*s.yield/100;
 const stakers=rule==='fixed'?revenue*s.fixed/100:(s.direct+s.fintech*fintechStaker)*s.yield/100;
 return {total,capital,oc,revenue,stakers,fintechRevenue:revenue-stakers,share:revenue?100*stakers/revenue:0,apr:capital?100*stakers/capital:0,fintechStaker:fintechStaker*100,required:total*s.target/100,impliedCapital:s.hurdle?stakers/(s.hurdle/100):0};
}
root.EUSD={defaults,calculate};if(typeof module!=='undefined')module.exports=root.EUSD;
})(typeof window!=='undefined'?window:globalThis);
