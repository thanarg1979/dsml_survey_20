import holoviews as hv
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

from textwrap import wrap

from typing import Any
from typing import Dict
from typing import Optional

from .paths import DATA
from .kaggle import REVERSE_SALARY_THRESHOLDS


SMALL_FONT = 12
MEDIUM_FONT = 18
BIG_FONT = 25
HUGE_FONT = 35


MPL_RC = {
    "font.size": SMALL_FONT,
    "axes.labelsize": BIG_FONT,
    "axes.titlesize": HUGE_FONT,
    "legend.fontsize": MEDIUM_FONT,
    "legend.title_fontsize": BIG_FONT,
    "xtick.labelsize": MEDIUM_FONT,
    "ytick.labelsize": MEDIUM_FONT,
}


def check_df_is_stacked(df: pd.DataFrame) -> None:
    if len(df) > 50:
        raise ValueError(f"You probably don't want to create a Bar plot with 50+ bins: {len(df)}")
    if len(df.columns) != 3 or set(df.columns[-2:]).difference(("source", "Number", "Percentage")):
        raise ValueError(f"The df does not seem to be comparing value_counts: {df.columns}")


def hv_plot_value_count_comparison(
    df: pd.DataFrame,
    title: Optional[str] = None,
) -> hv.Layout:
    check_df_is_stacked(df)
    column = df.columns[0]
    if title is None:
        title = column
    source1, source2 = df["source"].unique()
    # Stack dataframe for Bars plot
    plot = hv.Bars(data=df, kdims=[column, "source"], vdims=[df.columns[-1]], label=title)
    plot = plot.opts(
        width=900,
        height=600,
        fontsize=12,
        fontscale=1.0,
        xrotation=90,
        xlabel=f"{source1.capitalize()} VS {source2.capitalize()}",
        show_grid=True,
        show_legend=True,
        show_title=True,
        tools=["hover"],
    )
    layout = plot
    return layout


def get_mpl_rc(rc: Dict[str, Any]) -> Dict[str, Any]:
    mpl_rc = MPL_RC.copy()
    if rc is not None:
        mpl_rc.update(**rc)
    return mpl_rc


def sns_plot_value_count_comparison(
    df: pd.DataFrame, title: Optional[str] = None, order: Optional[list] = None, rc: Optional[Dict[str, Any]] = None
) -> None:
    check_df_is_stacked(df)
    column = df.columns[0]
    if title is None:
        title = column
    with sns.plotting_context("notebook", rc=get_mpl_rc(rc)):
        plot = sns.catplot(
            data=df,
            kind="bar",
            x=df.columns[0],
            order=order,
            #order=["0", "1-2", "3-5", "5-10", "10-20", "20+"], #eg for code_exp
            y=df.columns[-1],
            hue=df.columns[1],
            palette="dark",
            alpha=0.6,
            height=8,
            aspect=2.0,
            legend=False,
        )
        # plot.despine(left=True)
        plot.ax.legend(loc="best", title="Source")
        plot.ax.set_title(title)
        # plot.set_axis_labels(x_label, y_label)

        # adapted from: https://stackoverflow.com/questions/39444665/add-data-labels-to-seaborn-factor-plot
        for i, bar in enumerate(plot.ax.patches):
            h = bar.get_height()
            plot.ax.text(
                x=bar.get_x() + bar.get_width() / 2,
                y=h + 0.35,
                s=f"{h:.1f}",  # the label
                ha="center",
                va="center",
                # fontweight='bold',
            )


def sns_plot_salary_medians(
    df: pd.DataFrame, title: Optional[str] = None, rc: Optional[Dict[str, Any]] = None
) -> None:
    with sns.plotting_context("notebook", rc=get_mpl_rc(rc)):
        plot = sns.catplot(
            data=df,
            kind="bar",
            x="salary",
            y="country",
            hue="variable",
            orient="h",
            palette="dark",
            alpha=0.8,
            height=8,
            aspect=2.8,
            legend=False,
        )
        ticks = sorted(df.salary.unique(), reverse=True)
        #plot.ax.xticks(ticks, rotation="vertical")
        plt.xticks(ticks, rotation="vertical")
        #plt.xlim((0, 170000))
        x_labels = [REVERSE_SALARY_THRESHOLDS[sal] for sal in ticks]
        #wrapped_x_labels = ['\n'.join(wrap(l, 7)) for l in x_labels]
        wrapped_x_labels = [label.replace("-", "-\n") for label in x_labels]
        plot.ax.xaxis.set_ticklabels(wrapped_x_labels)
        #plot.ax.xaxis.set_ticklabels([REVERSE_SALARY_THRESHOLDS[sal] for sal in ticks])
        plot.ax.grid(axis="x")
        #plot.despine()
        plot.ax.set_axisbelow(True)
        plot.ax.set_box_aspect(12/len(plot.ax.patches))
        plot.ax.legend(loc="center left", title="", bbox_to_anchor=(1.04,0.5))
        plot.ax.legend(loc="best", title="")
        plot.ax.set_title(title)

        for i, bar in enumerate(plot.ax.patches):
            h = bar.get_height()
            w = bar.get_width()
            y = bar.get_y()
            plot.ax.annotate(
                text=f"${w:.0f}",
                xy=(w, y + h / 2),
                xycoords="data",
                ha='left',
                #va='center',
                va='center_baseline',
                # offset text 4pts to the left
                xytext=(4, 0),
                textcoords="offset points"
            )
        plt.setp(plot.ax.get_xticklabels(), rotation=30, horizontalalignment='center')
        plt.xticks(fontsize=12)
