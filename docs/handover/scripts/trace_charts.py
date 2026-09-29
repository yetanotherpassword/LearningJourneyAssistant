# Draws Figures 3 and 4 (10-stu0003-marks.png, 09-stu0003-profile.png). Run from docs/handover/diagrams with any Python that has matplotlib.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
INK="#0b0b0b"; INK2="#52514e"; MUTED="#9a9892"; GRID="#e6e5e1"; SURF="#ffffff"
BLUE="#2a78d6"; ORANGE="#eb6834"
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.edgecolor":GRID,"axes.labelcolor":INK2,
  "xtick.color":INK2,"ytick.color":INK2,"axes.spines.top":False,"axes.spines.right":False,"axes.spines.left":False})
comps=[("Object-Oriented Design and Implementation",62.7,"isolated gap"),
       ("Data Structures and Algorithms",63.7,"persistent gap"),
       ("Industry Standards Application",65.0,"developing"),
       ("Technical Communication and Documentation",65.1,"developing"),
       ("Project Management",66.0,"proficient")]
med, mad = 65.0, 1.0; cut = med - mad
fig,ax=plt.subplots(figsize=(8.2,3.3),dpi=220); fig.patch.set_facecolor(SURF)
ax.axvspan(61.5,cut,color="#eaf1fb",zorder=0)
ax.axvline(med,color=INK2,lw=1.2,zorder=1); ax.axvline(cut,color=BLUE,lw=1.2,ls="--",zorder=1)
ax.text(med+0.05,5.05,"student's median 65.0",ha="left",va="bottom",color=INK2,fontsize=8.5)
ax.text(cut-0.05,5.05,"cutoff = median − 1 MAD = 64.0",ha="right",va="bottom",color=INK2,fontsize=8.5)
ax.text(61.6,0.1,"gap zone",ha="left",va="center",color=BLUE,fontsize=8.5,style="italic")
for i,(name,v,cls) in enumerate(reversed(comps)):
    y=i+0.5; gap="gap" in cls
    ax.scatter([v],[y],s=90,color=BLUE if gap else MUTED,edgecolor=SURF,linewidth=2,zorder=3)
    ax.text(v+0.12,y,f"{v:.1f}%  {cls}",va="center",fontsize=8.5,color=INK if gap else INK2,fontweight="bold" if name.startswith("Data") else "normal",bbox=dict(boxstyle="square,pad=0.15",fc=SURF,ec="none"),zorder=4)
ax.set_yticks([i+0.5 for i in range(5)]); ax.set_yticklabels([c[0] for c in reversed(comps)],fontsize=8.5)
ax.set_ylim(0,5.4); ax.set_xlim(61.5,67.6)
ax.set_xlabel("Attainment in each competency (%)")
ax.tick_params(axis="y",length=0); ax.grid(axis="x",color=GRID,lw=0.8); ax.set_axisbelow(True)
fig.tight_layout(); fig.savefig("09-stu0003-profile.png",facecolor=SURF); plt.close(fig)

rows=[("CSE1OOF","Test",60,0.15),("CSE1OOF","Practical demonstration",63,0.20),("CSE1OOF","Assignment",65,0.25),("CSE1OOF","Central examination",62,0.40),
      ("CSE2ALG","Test",66,0.20),("CSE2ALG","Assignment",63,0.30),("CSE2ALG","Central examination",64,0.50)]
fig,ax=plt.subplots(figsize=(8.2,3.6),dpi=220); fig.patch.set_facecolor(SURF)
ys=list(range(len(rows)))[::-1]
for y,(subj,name,score,w) in zip(ys,rows):
    col=BLUE if subj=="CSE1OOF" else ORANGE
    ax.scatter([score],[y],s=40+400*w,color=col,edgecolor=SURF,linewidth=2,zorder=3)
    quoted = subj=="CSE2ALG" and name in ("Assignment","Central examination")
    ax.text(score+0.45,y,f"{score}  (weight {w:g})" + ("   quoted in the plan" if quoted else ""),va="center",fontsize=8.5,color=INK if quoted else INK2,fontweight="bold" if quoted else "normal",bbox=dict(boxstyle="square,pad=0.15",fc=SURF,ec="none"),zorder=4)
ax.axvline(63.7,color=INK2,lw=1.2,ls="--",zorder=1)
ax.text(63.75,len(rows)-0.45,"competency attainment 63.7%",ha="left",va="bottom",color=INK2,fontsize=8.5)
ax.set_yticks(ys); ax.set_yticklabels([f"{s}  {n}" for s,n,_,_ in rows],fontsize=8.5)
ax.set_ylim(-0.7,len(rows)+0.1); ax.set_xlim(58.5,72.5)
ax.set_xlabel("Score (%)   ·   dot area shows the assessment's weight within its subject")
ax.tick_params(axis="y",length=0); ax.grid(axis="x",color=GRID,lw=0.8); ax.set_axisbelow(True)
ax.legend(handles=[Line2D([],[],marker="o",ls="",color=BLUE,markersize=8,label="CSE1OOF"),Line2D([],[],marker="o",ls="",color=ORANGE,markersize=8,label="CSE2ALG")],
          loc="upper right",frameon=False,fontsize=8.5)
fig.tight_layout(); fig.savefig("10-stu0003-marks.png",facecolor=SURF); plt.close(fig)
print("ok")
