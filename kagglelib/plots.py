import functools
from textwrap import wrap
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

import matplotlib as mpl
import matplotlib.pyplot as plt
import natsort
import numpy as np
import pandas as pd
import seaborn as sns
import sklearn.neighbors

from importlib_metadata import version
from matplotlib.transforms import Bbox

from .paths import DATA
from .kaggle import SALARY_THRESHOLDS
from .kaggle import REVERSE_SALARY_THRESHOLDS
from .kaggle import fix_age_bin_distribution
from .kaggle import calc_avg_age_distribution


#PALETTE_USA_VS_ROW = [sns.desaturate("green", 0.75), "peru"]

PALETTE_INCOME_GROUP = sns.cubehelix_palette(10, rot=-.25, light=.7)
PALETTE_USA_VS_ROW = [sns.desaturate("lightcoral", 0.9), sns.desaturate("deepskyblue", 0.6)]
PALETTE_COMPARISON = [sns.desaturate(color, 0.4) for color in "red,magenta,cyan,blue,cornflowerblue,green".split(",")]
PALETTE_ORIGINAL_VS_FILTERED = [sns.desaturate("red", 0.4), sns.desaturate("cornflowerblue", 0.75)]

SMALL_FONT = 14
MEDIUM_FONT = 18
BIG_FONT = 24
HUGE_FONT = 30


MPL_RC = {
    "font.size": SMALL_FONT,
    "axes.labelsize": BIG_FONT,
    "axes.titlesize": HUGE_FONT,
    "legend.fontsize": MEDIUM_FONT,
    "legend.title_fontsize": BIG_FONT,
    "xtick.labelsize": MEDIUM_FONT,
    "ytick.labelsize": MEDIUM_FONT,
}

sns.set_style("dark", {'axes.linewidth': 0.5})


def check_df_is_stacked(df: pd.DataFrame) -> None:
    if len(df.columns) < 3:
        raise ValueError(f"The stacked dataframes need at least 3 columns: {df.columns}")
    if len(df) > 50:
        raise ValueError(f"You probably don't want to create a Bar plot with 50+ bins: {len(df)}")


def get_mpl_rc(rc: Dict[str, Any]) -> Dict[str, Any]:
    mpl_rc = MPL_RC.copy()
    if rc is not None:
        mpl_rc.update(**rc)
    return mpl_rc


def mpl_annotate(ax: mpl.axes.Axes, text: str, **kwargs) -> None:
    """
    Wrapper around ax.annotate() that uses the correct arguments regardless of the matplotlib version

    Matplotlib 3.0 changed the ax.annotate() function definition from:

    ``` diff
    - Axes.annotate(self, s, xy, *args, **kwargs)[source]
    + Axes.annotate(self, text, xy, *args, **kwargs)[source]
    ```

    In Matplotlib 3.0.2 the change was reverted.
    In Matplotlib 3.3 the change was reintroduced .

    ## Relevant links

    - https://matplotlib.org/3.0.0/api/_as_gen/matplotlib.axes.Axes.annotate.html
    - https://matplotlib.org/3.0.2/api/_as_gen/matplotlib.axes.Axes.annotate.html
    - https://matplotlib.org/3.2.0/api/_as_gen/matplotlib.axes.Axes.annotate.html
    - https://matplotlib.org/3.3.0/api/_as_gen/matplotlib.axes.Axes.annotate.html
    - https://github.com/matplotlib/matplotlib/issues/12325/
    - https://github.com/matplotlib/matplotlib/pull/12383
    """
    matplotlib_version = version("matplotlib")
    if matplotlib_version > "3.3":
        kwargs.update({"text": text})
    elif matplotlib_version <= "3.0.1":
        kwargs.update({"text": text})
    else:
        kwargs.update({"s": text})
    ax.annotate(**kwargs)


# adapted from: https://stackoverflow.com/questions/39444665/add-data-labels-to-seaborn-factor-plot
def _annotate_vertical_bar(bar, ax, fmt, annotation_mapping: Optional[Dict[Any, str]] = None):
    h = bar.get_height()
    w = bar.get_width()
    x = bar.get_x()
    if annotation_mapping:
        text = annotation_mapping[h]
    else:
        text = fmt.format(h)
    mpl_annotate(
        ax=ax,
        text=text,
        xy=(x + w / 2, h),
        xycoords="data",
        ha='center',
        va='center_baseline',
        # offset text 8pts to the top
        xytext=(0, 8),
        textcoords="offset points",
        fontweight="bold",
    )


def get_text_width(text: str, ax: mpl.axes.Axes) -> float:
    renderer = ax.figure.canvas.get_renderer()
    text_artist = mpl.text.Text(text=text, fontsize=SMALL_FONT, fontweight="bold", figure=ax.figure)
    bbox = text_artist.get_window_extent(renderer=renderer)
    # transform bounding box to data coordinates
    bbox = Bbox(ax.transData.inverted().transform(bbox))
    return bbox.width


def _annotate_horizontal_bar(bar, ax, fmt, annotation_mapping: Optional[Dict[Any, str]] = None) -> None:
    offset = 3  # pts
    h = bar.get_height()
    w = bar.get_width()
    y = bar.get_y()
    text = annotation_mapping[w] if annotation_mapping  else fmt.format(w)
    annotation_width = get_text_width(text, ax=ax)
    threshold = 1.1 * (annotation_width + offset * SMALL_FONT / 72)
    if threshold <= w:
        # annotation is short enough, put it inside the bar
        ha = "right"
        xytext = (-offset, 0)
        color = "white"
    else:
        # annotation too long, put it outside of the bar
        ha = "left"
        xytext = (offset, 0)
        color = "black"
    mpl_annotate(
        ax=ax,
        text=text,
        xy=(w, y + h / 2),
        xycoords="data",
        ha=ha,
        va='center',
        # offset text to the left or right
        xytext=xytext,
        textcoords="offset points",
        fontweight="bold",
        color=color,
    )


def _set_bar_width(bar, width: float) -> None:
    diff = bar.get_width() - width
    bar.set_width(width)  # we change the bar width
    bar.set_x(bar.get_x() + diff / 2)  # we recenter the bar


def sns_plot_value_count_comparison(
    df: pd.DataFrame,
    width: Optional[float] = None,
    height: Optional[float] = None,
    ax: Optional[mpl.axes.Axes] = None,
    title: Optional[str] = None,
    order_by_labels: bool = True,
    fmt: Optional[str] = None,
    rc: Optional[Dict[str, Any]] = None,
    orientation: str = "vertical",
    legend_location: Optional[str] = "best",
    x_ticklabels_rotation: Optional[float] = None,
    y_ticklabels_rotation: Optional[float] = None,
    bar_width: Optional[float] = None,
    title_wrap_length: Optional[int] = None,
    palette: sns.palettes._ColorPalette = PALETTE_ORIGINAL_VS_FILTERED,
    annotation_mapping: Optional[Dict[Any, str]] = None,
) -> None:
    if orientation not in {"horizontal", "vertical", "h", "v"}:
        raise ValueError(f"Orientation must be one of {'horizontal', 'vertical'}, not: {orientation}")
    if not ax:
        if not (width and height):
            raise ValueError("You must specify either an <ax> or both <width> and <height>")
    check_df_is_stacked(df)
    if fmt is None:
        fmt = "{:.1f}" if df.dtypes[-1] == 'float64' else "{:.0f}"
    if title is None:
        title = df.columns[0]
    if title_wrap_length:
        title = "\n".join(wrap(title, title_wrap_length))
    if orientation in {"horizontal", "h"}:
        x = df.columns[-1]
        y = df.columns[0]
        annotate_func = _annotate_horizontal_bar
        order = natsort.natsorted(df[y].unique())
    else:
        x = df.columns[0]
        y = df.columns[-1]
        annotate_func = _annotate_vertical_bar
        order = natsort.natsorted(df[x].unique())
    with sns.plotting_context("notebook", rc=get_mpl_rc(rc)):
        if ax is None:
            fig, ax = plt.subplots(figsize=(width, height))
        sns.barplot(
            data=df,
            ax=ax,
            x=x,
            y=y,
            hue=df.columns[1],
            order=order if order_by_labels else None,
            palette=palette,
        )
        if orientation in {"horizontal", "h"}:
            sns.despine(bottom=True)
            ax.tick_params(left=False, bottom=False)
            ax.xaxis.set_ticklabels("")
        else:
            sns.despine(left=True)
            ax.tick_params(left=False, bottom=False)
            ax.yaxis.set_ticklabels("")
        # Remove Labels from X and Y axes (we should have the relevant info on the title)
        ax.set_xlabel('')
        ax.set_ylabel('')

        if x_ticklabels_rotation:
            ax.set_xticklabels(ax.get_xticklabels(), rotation=x_ticklabels_rotation)
        if y_ticklabels_rotation:
            ax.set_yticklabels(ax.get_yticklabels(), rotation=y_ticklabels_rotation)
        if legend_location is None:
            ax.get_legend().remove()
        else:
            ax.legend(loc=legend_location, title="")
        ax.set_title(title)
        for bar in ax.patches:
            annotate_func(bar=bar, ax=ax, fmt=fmt, annotation_mapping=annotation_mapping)
            if bar_width:
                _set_bar_width(bar, width=bar_width)


def sns_plot_participants_vs_median_salary(
    no_participants_df: pd.DataFrame,
    median_salary_df: pd.DataFrame,
    width: Optional[float] = None,
    height: Optional[float] = None,
    title: Optional[str] = None,
    rc: Optional[Dict[str, Any]] = None,
    title_wrap_length: Optional[int] = None,
    palette: sns.palettes._ColorPalette = PALETTE_ORIGINAL_VS_FILTERED,
) -> None:
    with sns.plotting_context("notebook", rc=get_mpl_rc(rc)):
        fig, (ax1, ax2) = plt.subplots(nrows=1, ncols=2, sharey=True, figsize=(width, height), squeeze=True)
        sns_plot_value_count_comparison(
            median_salary_df,
            ax=ax1,
            orientation="h",
            order_by_labels=False,
            palette=PALETTE_COMPARISON,
            title="Median salary",
            legend_location="best",
            annotation_mapping=REVERSE_SALARY_THRESHOLDS
        )
        sns_plot_value_count_comparison(
            no_participants_df,
            ax=ax2,
            orientation="h",
            order_by_labels=False,
            palette=PALETTE_COMPARISON,
            title="No. participants",
            legend_location=None,
        )
        fig.subplots_adjust(top=0.80)
        fig.suptitle(title, fontsize=HUGE_FONT, y=1.04)
        plt.tight_layout()


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
            height=8,
            aspect=2.8,
            legend=False,
            order = reversed(df.country.unique()),
            hue_order=["Filtered", "Unfiltered"]
        )

        #ticks = sorted(df.salary.unique(), reverse=True)
        # plot.ax.xticks(ticks, rotation="vertical")
        #plt.xticks(ticks, rotation="vertical")
        #plt.xlim((0, 150000))
        #x_labels = [REVERSE_SALARY_THRESHOLDS[sal] for sal in ticks]
        #wrapped_x_labels = ['\n'.join(wrap(l, 7)) for l in x_labels]
        #wrapped_x_labels = [label.replace("-", "-\n") for label in x_labels]
        #plot.ax.xaxis.set_ticklabels(wrapped_x_labels)
        #plot.ax.xaxis.set_ticklabels([REVERSE_SALARY_THRESHOLDS[sal] for sal in ticks])
        plot.ax.xaxis.set_ticklabels("")
        plot.ax.tick_params(left=False, bottom=False)
        #plot.ax.grid(axis="x")
        plot.despine(bottom=True)
        # Remove Labels from X and Y axes (we should have the relevant info on the title)
        plot.ax.set_xlabel('')
        plot.ax.set_ylabel('')
        # plot.set(xticklabels=[])
        #plot.ax.set_axisbelow(True)
        plot.ax.set_box_aspect(12/len(plot.ax.patches))
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


def sns_plot_age_distribution(
    df: pd.DataFrame,
    width: float = 14,
    height: float = 10,
    title: str = "Age distribution",
    fmt: str = "{:.1f}",
    rc: Optional[Dict[str, Any]] = None,
    orientation: str = "vertical",
    bar_width: Optional[float] = None,
    title_wrap_length: Optional[int] = None,
) -> None:
    if title_wrap_length:
        title = "\n".join(wrap(title, title_wrap_length))
    default_distribution = (df.age.value_counts(True) * 100).sort_index().round(2)
    proposed_distribution = fix_age_bin_distribution(df, rename_index=True)
    avg_bin_distribution = calc_avg_age_distribution(df, rename_index=True)
    with sns.plotting_context("notebook", rc=get_mpl_rc(rc)):
        fig, (ax1, ax2, ax3) = plt.subplots(nrows=3, ncols=1, sharex=False, figsize=(width, height))
        color = sns.desaturate("darkred", 0.85)
        sns.barplot(
            x=default_distribution.index,
            y=default_distribution,
            ax=ax1,
            color=color,
        )
        sns.barplot(
            x=proposed_distribution.index,
            y=proposed_distribution,
            ax=ax2,
            color=color,
        )
        sns.barplot(
            x=avg_bin_distribution.index,
            y=avg_bin_distribution,
            ax=ax3,
            color=color,
        )
        ax1.yaxis.set_ticklabels("")
        ax2.yaxis.set_ticklabels("")
        ax3.yaxis.set_ticklabels("")
        sns.despine(ax=ax1, left=True, bottom=True)
        sns.despine(ax=ax2, left=True, bottom=True)
        sns.despine(ax=ax3, left=True, bottom=True)
        ax1.tick_params(left=False, bottom=False)
        ax2.tick_params(left=False, bottom=False)
        ax3.tick_params(left=False, bottom=False)
        ax1.set_title(title)
        ax1.set_ylabel("Default, %")
        ax2.set_ylabel("Adjusted, %")
        ax3.set_ylabel("Average, N")
        for ax in (ax1, ax2, ax3):
            ax1.set_ylim((0, 32))
            ax2.set_ylim((0, 32))
            ax3.set_ylim((0, 1150))
            ax.set_xlabel('')
            #ax.set_ylabel('')
            for bar in ax.patches:
                _annotate_vertical_bar(bar, ax, fmt)
                if bar_width:
                    _set_bar_width(bar, width=bar_width)
        for ax in (ax1, ax2, ax3):
            for i, bar in enumerate(ax.patches):
                if i >= 2:
                    break
                bar.set_color("darkcyan")


def sns_plot_global_salary_distribution_comparison(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    width: float,
    height: float,
    x1_limit: Optional[Tuple[float, float]] = (0, 19),
    x2_limit: Optional[Tuple[float, float]] = (0, 19),
    title: str = "Salary Distribution, $",
    fmt: str = "{:.1f}",
    rc: Optional[Dict[str, Any]] = None,
    orientation: str = "vertical",
    bar_width: Optional[float] = None,
    title_wrap_length: Optional[int] = None,
    label1: str = "Unfiltered",
    label2: str = "Filtered",
) -> None:
    if title_wrap_length:
        title = "\n".join(wrap(title, title_wrap_length))
    vc1 = (df1.salary.value_counts(True) * 100).round(2).sort_index().reset_index().rename(columns={"salary": "percentage", "index": "salary"})
    vc2 = (df2.salary.value_counts(True) * 100).round(2).sort_index().reset_index().rename(columns={"salary": "percentage", "index": "salary"})
    order = natsort.natsorted(vc1.salary.unique(), reverse=True)

    with sns.plotting_context("notebook", rc=get_mpl_rc(rc)):
        #with sns.axes_style("dark", {'axes.linewidth': 0.5}):
            fig, (ax1, ax2) = plt.subplots(nrows=1, ncols=2, sharex=False, figsize=(width, height), sharey=True, squeeze=True)
            sns.barplot(
                x=vc1.percentage,
                y=vc1.salary,
                ax=ax1,
                order=order,
                color=PALETTE_ORIGINAL_VS_FILTERED[0],
            )
            sns.barplot(
                x=vc2.percentage,
                y=vc2.salary,
                ax=ax2,
                order=order,
                color=PALETTE_ORIGINAL_VS_FILTERED[1],
            )

            ax1.set_title(label1)
            ax2.set_title(label2)
            ax1.xaxis.set_ticklabels("")
            ax2.xaxis.set_ticklabels("")
            ax1.xaxis.grid(True, which="major")
            ax2.xaxis.grid(True, which="major")
            #ax1.set_ylabel("Salary ($)")
            ax1.set_ylabel("")
            ax2.set_ylabel("")
            ax1.set_xlabel("")
            ax2.set_xlabel("")
            ax1.set_xlim((x1_limit))
            ax2.set_xlim((x2_limit))
            ax1.tick_params(left=False, bottom=False)
            ax2.tick_params(left=False, bottom=False)
            ax2.yaxis.set_tick_params(labeltop='on')
            fig.subplots_adjust(top=0.85)

            for ax in (ax1, ax2):
                for i, bar in enumerate(ax.patches):
                    _annotate_horizontal_bar(bar, ax, fmt)
                    if bar_width:
                        _set_bar_width(bar, width=bar_width)

            fig.suptitle(title, size=HUGE_FONT, y=1.03)
            plt.tight_layout()


def sns_plot_salary_pde_comparison_per_income_group(
    dataset: pd.DataFrame,
    width: float = 18,
    height: float = 10,
    title: str = "Salary PDE per WB income groups (log scale)",
    title_wrap_length: Optional[int] = None,
    bandwidth_adjust: Union[Union[int, float], Tuple[float, float, float, float, float]] = (0.8, 0.6, 0.5, 0.5, 0.5),
    log_scale: bool = True,
    rc: Optional[Dict[str, Any]] = None,
    palette: sns.palettes._ColorPalette = PALETTE_INCOME_GROUP,
) -> None:
    if title_wrap_length:
        title = "\n".join(wrap(title, title_wrap_length))
    if isinstance(bandwidth_adjust, (int, float)):
        bandwidth_adjust = [bandwidth_adjust] *  5
    dataset = dataset[~dataset.salary.isna() & ~(dataset.country == "Other")]
    # global_ = dataset.salary.reset_index(drop=True)
    india = dataset[(dataset.country == "India")].salary_threshold.reset_index(drop=True).rename("India")
    lower_middle = dataset[dataset.income_group.str.startswith("1") & (dataset.country != "India")].salary_threshold.reset_index(drop=True).rename("Lower Middle")
    upper_middle = dataset[dataset.income_group.str.startswith("2")].salary_threshold.reset_index(drop=True).rename("Upper Middle")
    high = dataset[dataset.income_group.str.startswith("3") & (dataset.country != "USA")].salary_threshold.reset_index(drop=True).rename("High")
    usa = dataset[(dataset.country == "USA")].salary_threshold.reset_index(drop=True).rename("USA")
    series = (usa, high, upper_middle, india, lower_middle)
    with sns.plotting_context("notebook", rc=get_mpl_rc(rc)):
        fig, axes = plt.subplots(nrows=5, ncols=1, sharex=True, figsize=(width, height))
        kdeplot_common = functools.partial(
            sns.kdeplot,
            log_scale=log_scale,
            clip_on=False,
            common_norm=False,
            palette=palette,
        )
        kdeplot = functools.partial(
            kdeplot_common,
            fill=True,
            alpha=1,
            linewidth=1.5,
        )
        kdeplot_line = functools.partial(
            kdeplot_common,
            color="w",
            linewidth=2.5,
        )
        for ax, sr, bw_adjust in zip(axes, series, bandwidth_adjust):
            kdeplot(ax=ax, data=sr, bw_adjust=bw_adjust)
            kdeplot_line(ax=ax, data=sr, bw_adjust=bw_adjust)
            ax.set_ylabel(sr.name, rotation=0, ha="right", va="center_baseline")
            ax.yaxis.set_ticklabels("")
            sns.despine(ax=ax, left=True, bottom=True)
            ax.tick_params(left=False, bottom=False)
            ax.xaxis.grid(True)
        ax.set_xlabel("")
        ax.xaxis.set_ticklabels("")
        fig.suptitle(title, size=HUGE_FONT)
        plt.tight_layout()


def sns_plot_pde_comparison(
    series: Union[pd.Series, List[pd.Series]],
    width: float = 18,
    height: float = 14,
    title: str = "Salary PDE per role (log scale)",
    title_wrap_length: Optional[int] = None,
    bandwidth: float = 10,
    log_scale: bool = True,
    rc: Optional[Dict[str, Any]] = None,
    palette: sns.palettes._ColorPalette = PALETTE_INCOME_GROUP,
) -> None:
    if title_wrap_length:
        title = "\n".join(wrap(title, title_wrap_length))
    if isinstance(series, pd.Series):
         series = [series]
    if not isinstance(bandwidth, (list, tuple)):
        bandwidth = [bandwidth] * len(series)
    with sns.plotting_context("notebook", rc=get_mpl_rc(rc)):
        fig, axes = plt.subplots(nrows=len(series), ncols=1, sharex=True, sharey=True, figsize=(width, height))
        for (sr, ax, bw) in zip(series, axes, bandwidth):
            x_d = np.array(sorted(SALARY_THRESHOLDS.values()))
            kde = sklearn.neighbors.KernelDensity(bandwidth=bw, kernel="gaussian")
            kde.fit(sr.values[:, None])
            logprob = kde.score_samples(x_d[:, None])
            ax.plot(x_d, np.exp(logprob), color="w", linewidth=2.5)
            ax.fill_between(x_d, np.exp(logprob), alpha=1, linewidth=1.5)
            ax.set_ylabel(sr.name, rotation=0, ha="right", va="center_baseline")
            sns.despine(ax=ax, left=True, bottom=True)
            ax.tick_params(left=False, bottom=False)
            ax.xaxis.grid(True, which="major")
            ax.yaxis.set_ticklabels("")
        if log_scale:
            ax.set_xscale('log')
        #ax.set_xlim((1, 1000000))
        fig.suptitle(title, size=HUGE_FONT)
        plt.tight_layout()


def sns_plot_salary_pde_comparison_per_role(
    dataset: pd.DataFrame,
    width: float = 18,
    height: float = 14,
    title: str = "Salary PDE per role (log scale)",
    title_wrap_length: Optional[int] = None,
    bandwidth_adjust: float = 0.6,
    log_scale: bool = True,
    rc: Optional[Dict[str, Any]] = None,
    palette: sns.palettes._ColorPalette = PALETTE_INCOME_GROUP,
) -> None:
    if title_wrap_length:
        title = "\n".join(wrap(title, title_wrap_length))
    dataset = dataset[~dataset.salary.isna() & ~(dataset.country == "Other")]
    roles = [
        "Business Analyst",
        "DBA/Database Engineer",
        "Data Analyst",
        "Data Engineer",
        "Data Scientist",
        "Machine Learning Engineer",
        "Research Scientist",
        "Software Engineer",
        "Product/Project Manager",
        "Statistician",
        "Other",
    ]
    series = map(lambda role: dataset[dataset.role == role].salary_threshold.reset_index(drop=True).rename(role), roles)
    with sns.plotting_context("notebook", rc=get_mpl_rc(rc)):
        fig, axes = plt.subplots(nrows=len(roles), ncols=1, sharex=True, figsize=(width, height))
        kdeplot_common = functools.partial(
            sns.kdeplot,
            log_scale=log_scale,
            bw_adjust=bandwidth_adjust,
            clip_on=False,
            common_norm=False,
            palette=palette,
        )
        kdeplot = functools.partial(
            kdeplot_common,
            fill=True,
            alpha=1,
            linewidth=1.5,
        )
        kdeplot_line = functools.partial(
            kdeplot_common,
            color="w",
            linewidth=2.5,
        )
        for ax, sr in zip(axes, series):
            kdeplot(ax=ax, data=sr)
            kdeplot_line(ax=ax, data=sr)
            ax.set_ylabel(sr.name, rotation=0, ha="right", va="center_baseline")
            ax.yaxis.set_ticklabels("")
            sns.despine(ax=ax, left=True, bottom=True)
            ax.tick_params(left=False, bottom=False)
            ax.grid(True)
        ax.set_xlabel("")
        fig.suptitle(title, size=HUGE_FONT)
        plt.tight_layout()


def sns_plot_salary_distribution_comparison(
    df: pd.DataFrame,
    width: float,
    height: float,
    x1_limit: Optional[Tuple[float, float]] = (0, 19),
    x2_limit: Optional[Tuple[float, float]] = (0, 19),
    title: str = "Salary Distribution, $",
    fmt: str = "{:.1f}",
    rc: Optional[Dict[str, Any]] = None,
    title_wrap_length: Optional[int] = None,
    label1: str = "Unfiltered",
    label2: str = "Filtered",
) -> None:
    """

    Plots a dataframe like this one:

    ```
               Lower Middle  Upper Middle  India  High  USA
    salary
    5000-7499         12.91          6.46  12.98  0.13  NaN
    4000-4999          7.24          3.38   7.45  0.13  NaN
    3000-3999          5.00          4.04   3.91   NaN  NaN
    2000-2999          5.90          4.85   4.27   NaN  NaN
    1000-1999         10.41          4.55   8.41   NaN  NaN
    ```

    """
    if title_wrap_length:
        title = "\n".join(wrap(title, title_wrap_length))
    series = [df[col] for col in df.columns]
    with sns.plotting_context("notebook", rc=get_mpl_rc(rc)):
        #with sns.axes_style("dark", {'axes.linewidth': 0.5}):
            fig, axes = plt.subplots(nrows=1, ncols=len(series), sharex=True, sharey=True, figsize=(width, height), squeeze=True)
            for (ax, sr, color) in zip(axes, series, PALETTE_COMPARISON):
                sns.barplot(
                    x=sr,
                    y=sr.index,
                    ax=ax,
                    color=color,
                )
                ax.set_ylabel("")
                ax.set_xlabel("")
                ax.set_title(sr.name)
                ax.xaxis.set_ticklabels("")
                ax.xaxis.grid(True)
            fig.suptitle(title, size=HUGE_FONT, y=1.03)
            plt.tight_layout()
            axes[-1].yaxis.set_tick_params(labeltop='on')
            for ax in axes:
                for i, bar in enumerate(ax.patches):
                    _annotate_horizontal_bar(bar, ax, fmt)
