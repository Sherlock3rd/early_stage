(() => {
  "use strict";

  const DIMENSIONS = ["阶段目标", "任务链", "核心循环", "渐进体验", "地图体验", "经济体验", "剧情轴"];
  const CURVE_COLORS = {
    emotion: "#f4a261",
    experience: "#65a9ff",
    trend: "#66e3c4"
  };
  const DATASET_ID_PATTERN = /^[a-z0-9][a-z0-9-]{0,63}$/;
  const state = {
    data: null,
    visible: [],
    selectedIndex: 0,
    activeDimension: "",
    galleryIndex: 0,
    curveVisibility: null,
    curveModel: null,
    curveSize: "",
    loopModel: null,
    loopSize: "",
    macroLoopVisibility: null
  };
  let lightboxController;
  const byId = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[char]));
  const formatTime = (seconds) => {
    const total = Math.max(0, Number(seconds));
    const minutes = Math.floor(total / 60);
    const remainder = Math.floor(total % 60);
    return `${minutes}:${String(remainder).padStart(2, "0")}`;
  };
  const exactValue = (value) => String(value || "").trim().toLocaleLowerCase();
  function resolveAnalysisDataPath(search, configured = "data.json") {
    const dataset = new URLSearchParams(String(search || "")).get("dataset");
    return dataset && DATASET_ID_PATTERN.test(dataset)
      ? `data/${dataset}.json`
      : configured;
  }

  function resolveCurrentDatasetId(search, configured = "data.json") {
    const requested = new URLSearchParams(String(search || "")).get("dataset");
    if (requested && DATASET_ID_PATTERN.test(requested)) return requested;
    const configuredMatch = String(configured).match(
      /^data\/([a-z0-9][a-z0-9-]{0,63})\.json$/
    );
    return configuredMatch ? configuredMatch[1] : "";
  }

  function normalizeDatasetManifest(payload, currentId = "") {
    const datasets = Array.isArray(payload?.datasets) ? payload.datasets : [];
    const normalized = [];
    datasets.forEach((entry) => {
      const id = String(entry?.id || "");
      if (!DATASET_ID_PATTERN.test(id) || normalized.some((item) => item.id === id)) {
        return;
      }
      const label = String(entry?.label || "").trim() || id;
      normalized.push({ id, label });
    });
    if (
      DATASET_ID_PATTERN.test(currentId)
      && !normalized.some((item) => item.id === currentId)
    ) {
      normalized.push({ id: currentId, label: currentId });
    }
    return normalized;
  }

  function datasetSwitchTarget(href, datasetId) {
    if (!DATASET_ID_PATTERN.test(String(datasetId || ""))) return "";
    try {
      const target = new URL(String(href));
      target.searchParams.set("dataset", datasetId);
      return target.toString();
    } catch {
      return "";
    }
  }

  function computeTimelineLayout(duration, slices) {
    return {
      nodes: slices.map((slice) => ({
        left: slice.start / duration * 100,
        width: (slice.end - slice.start) / duration * 100
      }))
    };
  }

  function timelineMilestoneMarkup(milestones, duration) {
    if (!Array.isArray(milestones) || !(Number(duration) > 0)) return "";
    return milestones.map((milestone) => {
      const timestamp = Number(milestone?.timestamp);
      const sliceIndex = Number(milestone?.slice_index);
      if (!Number.isFinite(timestamp) || timestamp < 0 || timestamp > duration) {
        return "";
      }
      if (!Number.isInteger(sliceIndex) || sliceIndex < 0) return "";
      const type = String(milestone?.type || "").replaceAll("_", "-");
      const label = String(milestone?.label || "").trim();
      const note = String(milestone?.note || "").trim();
      const position = timestamp / duration * 100;
      const title = `${label} · ${formatTime(timestamp)}${note ? ` · ${note}` : ""}`;
      return `<button class="timeline-milestone ${escapeHtml(type)}" data-slice="${sliceIndex}" style="left:${position}%" type="button" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}">
        <span>${escapeHtml(label)}<b>${formatTime(timestamp)}</b></span>
      </button>`;
    }).join("");
  }

  function classifyHighlights(slice) {
    const labels = [];
    const narrative = exactValue(slice.narrative_climax.judgement);
    const flow = exactValue(slice.flow.judgement);
    if (narrative === "climax") labels.push("narrative-high");
    if (narrative === "low") labels.push("narrative-low");
    if (flow === "flow_peak") labels.push("flow-high");
    return labels;
  }

  function aggregateStages(slices) {
    const stages = new Map();
    slices.forEach((slice, index) => {
      const range = slice.stage_range;
      const key = `${range.name}\u0000${range.start}\u0000${range.end}`;
      if (!stages.has(key)) stages.set(key, { ...range, firstIndex: index, goals: [] });
      const goals = stages.get(key).goals;
      const goal = String(slice.dimensions["阶段目标"].fact || "").trim();
      if (goal && !goals.includes(goal)) goals.push(goal);
    });
    return [...stages.values()];
  }

  function dimensionTabs(slice, activeDimension = "") {
    const firstAvailable = DIMENSIONS.find((dimension) =>
      String(slice.dimensions[dimension]?.fact || "").trim()
    ) || "";
    const active = String(slice.dimensions[activeDimension]?.fact || "").trim()
      ? activeDimension
      : firstAvailable;
    return DIMENSIONS.map((dimension) => ({
      name: dimension,
      description: String(slice.dimensions[dimension]?.fact || "").trim(),
      disabled: !String(slice.dimensions[dimension]?.fact || "").trim(),
      active: dimension === active
    }));
  }

  function encodeAssetPath(path) {
    return String(path).split("/").map((segment) => encodeURIComponent(segment)).join("/");
  }

  function lightboxViewModel(frame) {
    return { src: encodeAssetPath(frame.path), caption: formatTime(frame.timestamp) };
  }

  function detailViewModel(slice, activeDimension = "") {
    const tabs = dimensionTabs(slice, activeDimension);
    const active = tabs.find((tab) => tab.active);
    return {
      slice,
      dimension: active?.name || "",
      description: active?.description || "",
      tabs,
      screenshots: [slice.main_frame, ...slice.evidence_frames.slice(0, 3)],
      confidence: Math.round(slice.confidence * 100),
      questions: slice.open_questions
    };
  }

  function imageMarkupPure(frame, className = "") {
    if (!frame) return "";
    const lightbox = lightboxViewModel(frame);
    return `<span class="image-shell ${className}"><img src="${escapeHtml(lightbox.src)}" data-lightbox="${escapeHtml(lightbox.src)}" data-caption="${lightbox.caption}" tabindex="0" role="button" aria-label="${escapeHtml(`放大截图 ${lightbox.caption}`)}" alt="${escapeHtml(`时间片截图 ${lightbox.caption}`)}" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span class="image-error" hidden>图片加载失败</span></span>`;
  }

  function adjacentGalleryIndex(current, direction, count) {
    if (count <= 1) return 0;
    return (current + direction + count) % count;
  }

  function galleryViewModel(frames, currentIndex = 0) {
    const count = frames.length;
    const current = count ? ((currentIndex % count) + count) % count : 0;
    return {
      count,
      currentIndex: current,
      current: frames[current],
      previousIndex: adjacentGalleryIndex(current, -1, count),
      nextIndex: adjacentGalleryIndex(current, 1, count)
    };
  }

  function galleryPreviewMarkup(frame, position, index) {
    const image = lightboxViewModel(frame);
    return `<button class="gallery-preview ${position}" type="button" data-gallery-index="${index}" aria-label="${position === "previous" ? "查看上一张截图" : "查看下一张截图"}"><img src="${escapeHtml(image.src)}" alt="" aria-hidden="true"></button>`;
  }

  function galleryHtml(frames, currentIndex = 0) {
    const gallery = galleryViewModel(frames, currentIndex);
    if (!gallery.count) return "";
    const multiple = gallery.count > 1;
    const dots = multiple
      ? `<div class="gallery-dots">${frames.map((_, index) => `<button type="button" data-gallery-index="${index}" class="${index === gallery.currentIndex ? "active" : ""}" aria-label="查看第 ${index + 1} 张截图" aria-current="${index === gallery.currentIndex}"></button>`).join("")}</div>`
      : "";
    return `<div class="gallery" data-gallery-current-index="${gallery.currentIndex}">
      <div class="gallery-stage">
        ${multiple ? galleryPreviewMarkup(frames[gallery.previousIndex], "previous", gallery.previousIndex) : ""}
        ${imageMarkupPure(gallery.current, "gallery-current")}
        ${multiple ? galleryPreviewMarkup(frames[gallery.nextIndex], "next", gallery.nextIndex) : ""}
        ${multiple ? `<button class="gallery-arrow previous" type="button" data-gallery-direction="-1" aria-label="上一张截图">‹</button><button class="gallery-arrow next" type="button" data-gallery-direction="1" aria-label="下一张截图">›</button>` : ""}
      </div>
      <div class="gallery-footer"><span>${gallery.currentIndex + 1} / ${gallery.count}</span>${dots}</div>
    </div>`;
  }

  function restoreGalleryFocus(container) {
    const currentImage = container.querySelector(".gallery-current [data-lightbox]");
    if (!currentImage) return false;
    currentImage.focus({ preventScroll: true });
    return true;
  }

  function tabsMarkup(tabs) {
    return tabs.map((tab) => `<button class="dimension-tab${tab.active ? " active" : ""}" type="button" role="tab" data-dimension="${escapeHtml(tab.name)}" aria-selected="${tab.active}" ${tab.disabled ? "disabled" : ""}>${escapeHtml(tab.name)}</button>`).join("");
  }

  function detailHtml(slice, activeDimension = "") {
    const detail = detailViewModel(slice, activeDimension);
    const questions = detail.questions.length
      ? `<section class="questions"><h3>待确认项</h3><ul>${detail.questions.map((question) => `<li>${escapeHtml(question)}</li>`).join("")}</ul></section>`
      : "";
    return `
      ${galleryHtml(detail.screenshots, 0)}
      <aside class="slice-meta">
        <div class="confidence"><span>置信度</span><strong>${detail.confidence}%</strong></div>
        ${questions}
      </aside>
      <div class="dimension-tabs" role="tablist">${tabsMarkup(detail.tabs)}</div>
      <section class="dimension-description" role="tabpanel"><p>${escapeHtml(detail.description)}</p></section>`;
  }

  function adjacentVisibleIndex(current, direction, visible) {
    let candidate = current + direction;
    while (candidate >= 0 && candidate < visible.length) {
      if (visible[candidate]) return candidate;
      candidate += direction;
    }
    return current;
  }

  function firstVisibleIndexInStage(stageName, slices, visible) {
    return slices.findIndex((slice, index) =>
      visible[index] && slice.stage_range.name === stageName
    );
  }

  function selectedIndexForVisible(current, visible) {
    if (current >= 0 && visible[current]) return current;
    return visible.findIndex(Boolean);
  }

  function timelineKeyDirection(event) {
    const tagName = String(event.target?.tagName || "").toUpperCase();
    if (["INPUT", "SELECT", "TEXTAREA"].includes(tagName) || event.target?.isContentEditable) return 0;
    if (event.key === "ArrowLeft") return -1;
    if (event.key === "ArrowRight") return 1;
    return 0;
  }

  const effectiveExperienceScore = (point) =>
    Number(point.experience.effective_score);

  function stageAverageExperienceObservations(
    slices,
    curvePoints,
    endTime = Number.POSITIVE_INFINITY
  ) {
    const stages = new Map();
    slices.forEach((slice, index) => {
      const range = slice.stage_range;
      const stageId = String(range.stage_id);
      if (!stages.has(stageId)) {
        stages.set(stageId, {
          time: (
            Number(range.start) + Math.min(Number(range.end), Number(endTime))
          ) / 2,
          total: 0,
          count: 0
        });
      }
      const stage = stages.get(stageId);
      stage.total += effectiveExperienceScore(curvePoints[index]);
      stage.count += 1;
    });
    return [...stages.entries()].map(([stageId, stage]) => ({
      time: stage.time,
      score: stage.total / stage.count,
      stageId,
      count: stage.count
    }));
  }

  function linearRegressionTrend(observations, min, max, predictionTimes = null) {
    if (!observations.length) {
      return {
        slope: 0,
        intercept: 0,
        predictions: [],
        rawOpeningPrediction: 0,
        rawEndingPrediction: 0,
        openingPrediction: 0,
        endingPrediction: 0,
        delta: 0,
        direction: "flat"
      };
    }
    const normalized = observations.map((item) => ({
      time: Number(item.time),
      score: Number(item.score)
    }));
    const meanX = normalized.reduce((sum, item) => sum + item.time, 0) / normalized.length;
    const meanY = normalized.reduce((sum, item) => sum + item.score, 0) / normalized.length;
    const denominator = normalized.reduce(
      (sum, item) => sum + (item.time - meanX) ** 2,
      0
    );
    const slope = denominator
      ? normalized.reduce(
        (sum, item) => sum + (item.time - meanX) * (item.score - meanY),
        0
      ) / denominator
      : 0;
    const intercept = meanY - slope * meanX;
    const predict = (time) => slope * Number(time) + intercept;
    const clamp = (value) => Math.min(Number(max), Math.max(Number(min), value));
    const outputTimes = Array.isArray(predictionTimes) && predictionTimes.length
      ? predictionTimes.map(Number)
      : normalized.map((item) => item.time);
    const rawOpeningPrediction = predict(outputTimes[0]);
    const rawEndingPrediction = predict(outputTimes[outputTimes.length - 1]);
    const openingPrediction = clamp(rawOpeningPrediction);
    const endingPrediction = clamp(rawEndingPrediction);
    const delta = endingPrediction - openingPrediction;
    return {
      slope,
      intercept,
      predictions: outputTimes.map((time) => clamp(predict(time))),
      rawOpeningPrediction,
      rawEndingPrediction,
      openingPrediction,
      endingPrediction,
      delta,
      direction: delta >= 0.5 ? "rising" : delta <= -0.5 ? "falling" : "flat"
    };
  }

  function defaultGlobalCurveVisibility() {
    return { emotion: true, experience: true, trend: true };
  }

  function updateGlobalCurveVisibility(current, action) {
    const next = { ...current };
    if (action.type === "toggle" && ["emotion", "experience", "trend"].includes(action.series)) {
      next[action.series] = !next[action.series];
    } else if (action.type === "all") {
      Object.keys(next).forEach((series) => { next[series] = true; });
    }
    return next;
  }

  function globalCurvesViewModel(data, width = 1000, height = 360) {
    width = Number(width);
    height = Number(height);
    const padding = { left: 54, right: 18, top: 36, bottom: 38 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const duration = Number(data.video.duration_seconds);
    const curve = data.global_curves;
    const min = Number(curve.scale.min);
    const max = Number(curve.scale.max);
    const scoreY = (score) => padding.top + (max - Number(score)) / (max - min) * plotHeight;
    const timeX = (seconds) => padding.left + Number(seconds) / duration * plotWidth;
    const slgMilestone = (data.timeline_milestones || []).find(
      (milestone) => milestone.type === "slg_entry"
    );
    const trendEndTime = slgMilestone
      ? Number(slgMilestone.timestamp)
      : duration;
    const trendEndSliceIndex = slgMilestone
      ? Number(slgMilestone.slice_index)
      : curve.points.length - 1;
    const trendSlices = data.slices.slice(0, trendEndSliceIndex + 1);
    const trendCurvePoints = curve.points.slice(0, trendEndSliceIndex + 1);
    const firstPredictionTime = (
      Number(curve.points[0].start) + Number(curve.points[0].end)
    ) / 2;
    const stageObservations = stageAverageExperienceObservations(
      trendSlices,
      trendCurvePoints,
      trendEndTime
    );
    const trendSummary = linearRegressionTrend(
      stageObservations,
      min,
      max,
      [firstPredictionTime, trendEndTime]
    );
    trendSummary.sampleBasis = "stage_average";
    trendSummary.sampleCount = stageObservations.length;
    trendSummary.endTime = trendEndTime;
    trendSummary.endLabel = slgMilestone ? "大地图入口" : "录屏结束";
    const predictTrend = (time) => Math.min(
      max,
      Math.max(min, trendSummary.slope * Number(time) + trendSummary.intercept)
    );
    const points = curve.points.map((point, index) => {
      const slice = data.slices[index];
      const midpoint = (Number(point.start) + Number(point.end)) / 2;
      const experienceTrend = index <= trendEndSliceIndex
        ? predictTrend(Math.min(midpoint, trendEndTime))
        : null;
      return {
        index,
        start: Number(point.start),
        end: Number(point.end),
        narrativeScore: Number(point.emotion.narrative_score),
        supportingScore: Number(point.emotion.supporting_score),
        emotionIntensity: Number(point.emotion.intensity),
        emotionDrivers: [...point.emotion.drivers],
        valence: point.emotion.valence,
        emotionEvent: point.emotion.event,
        emotionReason: point.emotion.reason,
        experienceScore: effectiveExperienceScore(point),
        experienceBaseScore: Number(point.experience.score),
        progressionPull: { ...point.experience.progression_pull },
        progressionBonus: Number(point.experience.adjustments.progression_bonus),
        repetitionPenalty: Number(point.experience.adjustments.repetition_penalty),
        effectiveRepeatCount: Number(
          point.experience.adjustments.effective_repeat_count
        ),
        repetitionContext: { ...point.experience.repetition_context },
        experienceTrend,
        experienceBasis: { ...point.experience.basis },
        experienceSummary: point.experience.summary,
        climax: exactValue(slice.narrative_climax.judgement) === "climax",
        flowPeak: exactValue(slice.flow.judgement) === "flow_peak",
        x: timeX(midpoint),
        y: {
          emotion: scoreY(point.emotion.intensity),
          experience: scoreY(effectiveExperienceScore(point)),
          trend: experienceTrend === null ? null : scoreY(experienceTrend)
        }
      };
    });
    return {
      width,
      height,
      padding,
      plotWidth,
      plotHeight,
      min,
      max,
      duration,
      colors: { ...CURVE_COLORS },
      points,
      trendPoints: points.length ? [
        {
          x: timeX(firstPredictionTime),
          y: { trend: scoreY(trendSummary.openingPrediction) }
        },
        {
          x: timeX(trendEndTime),
          y: { trend: scoreY(trendSummary.endingPrediction) }
        }
      ] : [],
      trendEndTime,
      trendEndSliceIndex,
      trendSummary
    };
  }

  function curvePath(points, name) {
    return points.map((point, index) =>
      `${index ? "L" : "M"}${point.x.toFixed(2)},${point.y[name].toFixed(2)}`
    ).join(" ");
  }

  function curveSliceBands(model) {
    const plotLeft = model.padding.left;
    const plotRight = model.width - model.padding.right;
    return model.points.map((point, index) => {
      const previous = model.points[index - 1];
      const following = model.points[index + 1];
      const left = previous ? (previous.x + point.x) / 2 : plotLeft;
      const right = following ? (point.x + following.x) / 2 : plotRight;
      return {
        index: point.index,
        left,
        right,
        top: model.padding.top,
        width: right - left,
        height: model.plotHeight,
        center: point.x
      };
    });
  }

  function curveSliceInteractionState(index, selectedIndex, visible) {
    return {
      selected: index === selectedIndex,
      filteredOut: !visible[index],
      disabled: !visible[index]
    };
  }

  function globalCurvesSvgMarkup(model, visibility) {
    const axisTicks = [0, 1, 2, 3, 4, 5].map((score) => {
      const y = model.padding.top + (model.max - score) / (model.max - model.min) * model.plotHeight;
      return `<g class="emotion-axis-tick"><line x1="${model.padding.left}" x2="${model.width - model.padding.right}" y1="${y}" y2="${y}"></line><text x="${model.padding.left - 10}" y="${y + 4}">${score}</text></g>`;
    }).join("");
    const labelStep = Math.max(1, Math.ceil(model.points.length / 12));
    const timeLabels = model.points.map((point, index) =>
      index % labelStep === 0 || index === model.points.length - 1
        ? `<text class="emotion-time-label" x="${point.x}" y="${model.height - 12}">${formatTime(point.start)}</text>`
        : ""
    ).join("");
    const emotionLine = visibility.emotion
      ? `<path class="global-emotion-line" d="${curvePath(model.points, "emotion")}"></path>`
      : "";
    const experienceLine = visibility.experience
      ? `<path class="global-experience-line" d="${curvePath(model.points, "experience")}"></path>`
      : "";
    const trendLine = visibility.trend
      ? `<path class="global-trend-line" d="${curvePath(model.trendPoints, "trend")}"></path>`
      : "";
    const emotionNodes = visibility.emotion
      ? model.points.map((point) =>
        `<circle class="global-emotion-point valence-${escapeHtml(point.valence)}" cx="${point.x}" cy="${point.y.emotion}" r="5"></circle>`
      ).join("")
      : "";
    const climaxMarkers = visibility.emotion ? model.points.filter((point) => point.climax).map((point) =>
      `<rect class="climax-marker" x="${point.x - 6}" y="${point.y.emotion - 6}" width="12" height="12" transform="rotate(45 ${point.x} ${point.y.emotion})"></rect>`
    ).join("") : "";
    const flowMarkers = visibility.experience ? model.points.filter((point) => point.flowPeak).map((point) =>
      `<text class="flow-marker" x="${point.x}" y="${Math.max(model.padding.top + 18, point.y.experience - 9)}">★</text>`
    ).join("") : "";
    const bands = curveSliceBands(model);
    const nodes = bands.map((band, index) => {
      const point = model.points[index];
      return `<rect class="curve-slice-hit-zone" data-curve-slice="${point.index}" x="${band.left}" y="${band.top}" width="${band.width}" height="${band.height}" tabindex="0" role="button" aria-describedby="emotion-curve-tooltip" aria-label="${escapeHtml(`${formatTime(point.start)} 至 ${formatTime(point.end)}，情绪强度 ${point.emotionIntensity.toFixed(1)}，体验强度 ${point.experienceScore.toFixed(1)}`)}"></rect><line class="curve-slice-guide" x1="${band.center}" x2="${band.center}" y1="${band.top}" y2="${band.top + band.height}"></line>`;
    }).join("");
    return `<svg class="emotion-curve-chart" viewBox="0 0 ${model.width} ${model.height}" role="img" aria-label="全局情绪与体验曲线">
      ${axisTicks}
      ${timeLabels}
      ${emotionLine}${experienceLine}${trendLine}
      ${emotionNodes}${climaxMarkers}${flowMarkers}
      ${nodes}
    </svg>`;
  }

  function globalCurvesLegendMarkup(visibility) {
    const labels = { emotion: "情绪强度", experience: "体验实际值", trend: "体验趋势" };
    const series = Object.keys(labels).map((name) =>
      `<button type="button" class="emotion-legend-item${visibility[name] ? " active" : ""}" data-curve-series-toggle="${name}" aria-pressed="${visibility[name]}"><i style="background:${CURVE_COLORS[name]}"></i>${labels[name]}</button>`
    ).join("");
    return `<div class="emotion-legend-series">${series}</div><div class="emotion-legend-actions"><button type="button" data-curve-action="all">显示全部</button></div>`;
  }

  function globalCurvesTooltipMarkup(point) {
    const valenceLabels = {
      positive: "正向", negative: "负向", mixed: "混合", neutral: "中性"
    };
    const driverLabels = {
      narrative: "剧情",
      environment_pressure: "环境压力",
      urgency: "紧迫目标",
      combat: "战斗冲突",
      progression_reward: "成长奖励",
      relief: "危机缓解"
    };
    const drivers = (point.emotionDrivers || [])
      .map((driver) => driverLabels[driver] || driver)
      .map(escapeHtml)
      .join(" / ");
    const trendText = Number.isFinite(point.experienceTrend)
      ? `回归预测 ${Number(point.experienceTrend).toFixed(2)}`
      : "已超出大地图入口回归范围";
    return `<strong>${formatTime(point.start)}–${formatTime(point.end)}</strong>
      <div class="curve-tooltip-head"><span>情绪强度 ${Number(point.emotionIntensity).toFixed(1)} · ${escapeHtml(valenceLabels[point.valence] || point.valence)}</span><span>有效体验 ${Number(point.experienceScore).toFixed(1)} · ${trendText}</span></div>
      <div class="emotion-tooltip-scores"><span>剧情刺激 ${Number(point.narrativeScore).toFixed(1)}</span><span>其他刺激 ${Number(point.supportingScore).toFixed(1)}</span>${drivers ? `<span>刺激来源 ${drivers}</span>` : ""}</div>
      ${point.emotionEvent ? `<p><b>主要刺激：</b>${escapeHtml(point.emotionEvent)}<br><b>评分原因：</b>${escapeHtml(point.emotionReason)}</p>` : ""}
      <div class="experience-adjustments">
        <span><b>原始即时分：</b>${Number(point.experienceBaseScore).toFixed(1)}</span>
        <span><b>渐进期待：</b>${Number(point.progressionPull.score).toFixed(1)} · 渐进奖励 +${Number(point.progressionBonus).toFixed(1)}</span>
        <span><b>重复疲劳：</b>重复惩罚 -${Number(point.repetitionPenalty).toFixed(1)} · 有效重复 ${Number(point.effectiveRepeatCount)} 次</span>
        <span><b>重复变化：</b>${escapeHtml(point.repetitionContext.variation)}</span>
        <span><b>重复依据：</b>${escapeHtml(point.repetitionContext.reason)}</span>
        <span><b>有效体验：</b>${Number(point.experienceScore).toFixed(1)}</span>
        <span><b>期待依据：</b>${escapeHtml(point.progressionPull.reason)}</span>
      </div>
      <div class="experience-basis">
        <span><b>玩法浓度：</b>${escapeHtml(point.experienceBasis.gameplay_concentration)}</span>
        <span><b>反馈密度：</b>${escapeHtml(point.experienceBasis.feedback_density)}</span>
        <span><b>目标/挑战：</b>${escapeHtml(point.experienceBasis.goal_challenge)}</span>
        <span><b>打断情况：</b>${escapeHtml(point.experienceBasis.interruption)}</span>
      </div>
      <p>${escapeHtml(point.experienceSummary)}</p>`;
  }

  function shouldDismissEmotionTooltip(event) {
    return event.key === "Escape";
  }

  function curveTooltipPlacement(
    point,
    model,
    containerWidth = model.width,
    tooltipWidth = 430
  ) {
    const topY = Math.min(point.y.emotion, point.y.experience);
    const horizontalMargin = 8;
    const halfWidth = Math.min(
      Number(tooltipWidth) / 2,
      Math.max(0, Number(containerWidth) / 2 - horizontalMargin)
    );
    const rawLeftPx = point.x / model.width * Number(containerWidth);
    const leftPx = Math.min(
      Number(containerWidth) - halfWidth - horizontalMargin,
      Math.max(halfWidth + horizontalMargin, rawLeftPx)
    );
    const leftPercent = Number(containerWidth)
      ? leftPx / Number(containerWidth) * 100
      : 50;
    const topPercent = topY / model.height * 100;
    return {
      leftPx,
      leftPercent,
      topPercent,
      below: topPercent < 30
    };
  }

  function globalCurvesGuideMarkup() {
    return `<p><strong>情绪强度 0～5：</strong>以剧情为主体，最终分由70%剧情刺激与30%较高刺激计算；其他刺激包含环境压力、紧迫目标、战斗、成长奖励和危机缓解。</p><p><strong>有效体验强度 0～5：</strong>体验线展示已经计入渐进期待奖励和重复疲劳惩罚的有效体验强度；原始即时分保留在 Tooltip 中。前 20 分钟或同类玩法前 5 次不衰减；partial_break 部分恢复重复计数，full_break 完全重置重复计数。</p><p><strong>体验整体趋势：</strong>统计范围从录屏开始到首次进入SLG大地图，包含入口所在时间片；先计算范围内各阶段的有效体验平均分，再让每个阶段以相同权重参与真实时间线性回归。入口后的实际折线继续保留，但不参与回归。</p>`;
  }

  function experienceTrendSummaryMarkup(trend) {
    const labels = { rising: "上升", flat: "持平", falling: "下降" };
    return `
        <span>回归起点 <strong>${trend.openingPrediction.toFixed(2)}</strong></span>
        <span>${escapeHtml(trend.endLabel)} ${formatTime(trend.endTime)} <strong>${trend.endingPrediction.toFixed(2)}</strong></span>
        <span>变化 <strong>${trend.delta >= 0 ? "+" : ""}${trend.delta.toFixed(2)}</strong></span>
        <b class="trend-${trend.direction}">${labels[trend.direction]}</b>`;
  }

  function loadInitialData(fetcher, onData, onError) {
    return Promise.resolve().then(fetcher).then(onData).catch(onError);
  }

  function createLightboxController(elements) {
    const {
      lightbox, lightboxClose, lightboxImage, lightboxCaption, documentRef
    } = elements;
    let lightboxTrigger = null;
    function openLightbox(trigger, src, caption) {
      lightboxTrigger = trigger || null;
      lightboxImage.hidden = false;
      lightboxImage.src = src;
      lightboxCaption.textContent = caption;
      lightbox.showModal();
      lightboxClose.focus();
    }
    function closeLightbox() {
      if (lightbox.open) lightbox.close();
      if (lightboxTrigger) lightboxTrigger.focus();
      lightboxTrigger = null;
    }
    function activateImage(event) {
      if (event.type === "keydown" && !["Enter", " "].includes(event.key)) return;
      const image = event.target.closest("[data-lightbox]");
      if (!image) return;
      event.preventDefault();
      openLightbox(image, image.dataset.lightbox, image.dataset.caption);
    }
    lightboxClose.addEventListener("click", closeLightbox);
    lightbox.addEventListener("cancel", (event) => {
      event.preventDefault();
      closeLightbox();
    });
    documentRef.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && lightbox.open) {
        event.preventDefault();
        closeLightbox();
      }
    });
    return { activateImage, openLightbox, closeLightbox };
  }

  function globalLoopInteractionState(sliceIndices, visible) {
    const enabledIndex = sliceIndices.find((index) => visible[index]);
    return {
      disabled: enabledIndex === undefined,
      primarySlice: enabledIndex === undefined ? sliceIndices[0] : enabledIndex
    };
  }

  function defaultMacroLoopVisibility(macros) {
    if (!Array.isArray(macros)) return {};
    return Object.fromEntries(macros.map((macro) => [macro.id, true]));
  }

  function updateMacroLoopVisibility(current, macroId) {
    return { ...current, [macroId]: current[macroId] === false };
  }

  function showAllMacroLoops(current) {
    return Object.fromEntries(Object.keys(current).map((macroId) => [macroId, true]));
  }

  function macroLoopLegendMarkup(macros) {
    const toggles = macros.map((macro) => `
      <button type="button" class="macro-loop-toggle macro-toggle-${escapeHtml(macro.accent.replaceAll("_", "-"))}"
        data-macro-loop-toggle="${escapeHtml(macro.id)}"
        aria-pressed="${macro.visible ? "true" : "false"}">
        <span aria-hidden="true"></span>
        <strong>${escapeHtml(macro.title)}</strong>
        <small>${macro.visible ? "已突出" : "已淡化"}</small>
      </button>
    `).join("");
    return `${toggles}<button type="button" class="macro-loop-show-all"
      data-macro-loop-action="show-all">显示全部</button>`;
  }

  function loopFamilyStatistics(graph) {
    const microLoops = graph.nodes.filter((node) => node.type === "micro_loop");
    const counts = new Map();
    microLoops.forEach((node) => {
      counts.set(node.loop_family_id, (counts.get(node.loop_family_id) || 0) + 1);
    });
    const families = graph.loop_families
      .filter((family) => counts.has(family.id))
      .map((family) => ({
        ...family,
        occurrences: counts.get(family.id),
        reinforcements: Math.max(counts.get(family.id) - 1, 0)
      }));
    return {
      eventCount: microLoops.length,
      uniqueCount: families.length,
      families
    };
  }

  function loopFamilyStatisticsMarkup(statistics) {
    const families = statistics.families.map((family) => `
      <article class="loop-family-stat family-accent-${escapeHtml(family.accent.replaceAll("_", "-"))}">
        <strong>${escapeHtml(family.title)}</strong>
        <span>出现 ${family.occurrences} 次 · 强化 ${family.reinforcements} 次</span>
      </article>
    `).join("");
    return `
      <div class="loop-stat-summary">
        <span>事件级小 LOOP <strong>${statistics.eventCount}</strong></span>
        <span>去重小 LOOP <strong>${statistics.uniqueCount}</strong></span>
      </div>
      <div class="loop-family-stat-list">${families}</div>`;
  }

  function relatedMicroLoops(nodes, sliceIndex, visible) {
    return nodes
      .filter((node) =>
        node.type === "micro_loop" && node.slice_indices.includes(sliceIndex)
      )
      .map((node) => ({
        id: node.id,
        title: node.title,
        disabled: !node.slice_indices.some((index) => visible[index])
      }));
  }

  function relatedLoopNavigationMarkup(items) {
    if (!items.length) {
      return '<span class="related-loop-empty">当前时间片无关联 LOOP</span>';
    }
    return `
      <strong class="related-loop-label">关联 LOOP</strong>
      ${items.map((item) => `
        <button type="button" class="related-loop-link"
          data-related-loop="${escapeHtml(item.id)}"
          aria-disabled="${item.disabled ? "true" : "false"}"
          ${item.disabled ? "disabled" : ""}>${escapeHtml(item.title)}</button>
      `).join("")}`;
  }

  function macroLoopSegments(nodes) {
    const counters = {};
    const segments = [];
    let active = null;
    nodes.forEach((node) => {
      if (node.type !== "micro_loop") {
        active = null;
        return;
      }
      if (!active || active.macroLoopId !== node.macro_loop_id) {
        const sequence = counters[node.macro_loop_id] || 0;
        counters[node.macro_loop_id] = sequence + 1;
        active = {
          id: `${node.macro_loop_id}:${sequence}`,
          macroLoopId: node.macro_loop_id,
          nodeIds: []
        };
        segments.push(active);
      }
      active.nodeIds.push(node.id);
    });
    return segments;
  }

  function hierarchicalLoopsViewModel(data, visible, macroVisibility) {
    const graph = data.global_loops;
    const macroById = Object.fromEntries(
      graph.macro_loops.map((macro) => [macro.id, macro])
    );
    const titleById = Object.fromEntries(
      graph.nodes.map((node) => [node.id, node.title])
    );
    const macroIdByNode = Object.fromEntries(
      graph.nodes.map((node) => [node.id, node.macro_loop_id])
    );
    const nodes = graph.nodes.map((node) => {
      const interaction = globalLoopInteractionState(node.slice_indices, visible);
      const referencedSlices = node.slice_indices.map((index) => data.slices[index]);
      const timeRange = `${formatTime(Math.min(...referencedSlices.map((slice) => slice.start)))}–${formatTime(Math.max(...referencedSlices.map((slice) => slice.end)))}`;
      const macro = node.macro_loop_id ? macroById[node.macro_loop_id] : null;
      return {
        ...node,
        ...interaction,
        macro,
        accent: macro?.accent || "",
        dimmed: Boolean(macro && macroVisibility[macro.id] === false),
        timeLabel: referencedSlices.length === 1
          ? timeRange
          : `${timeRange} · ${referencedSlices.length}个片段`,
        evidence: [...node.evidence_frames],
        parts: node.type === "micro_loop" ? [
          { key: "motivation", label: "动机", values: [node.motivation] },
          { key: "behavior", label: "行为", values: node.behaviors },
          { key: "reward", label: "奖励", values: [node.reward] },
          { key: "next", label: "下一动机", values: [node.next_motivation] }
        ] : []
      };
    });
    const segments = macroLoopSegments(nodes).map((segment) => ({
      ...segment,
      macro: macroById[segment.macroLoopId],
      dimmed: macroVisibility[segment.macroLoopId] === false
    }));
    const segmentIdByNode = Object.fromEntries(
      segments.flatMap((segment) =>
        segment.nodeIds.map((nodeId) => [nodeId, segment.id])
      )
    );
    nodes.forEach((node) => {
      node.segmentId = segmentIdByNode[node.id] || "";
    });
    const edges = graph.edges.map((edge) => {
      const fromMacroId = macroIdByNode[edge.from];
      const toMacroId = macroIdByNode[edge.to];
      return {
        ...edge,
        fromTitle: titleById[edge.from],
        toTitle: titleById[edge.to],
        fromMacroId,
        toMacroId,
        dimmed: Boolean(
          (fromMacroId && macroVisibility[fromMacroId] === false)
          || (toMacroId && macroVisibility[toMacroId] === false)
        ),
        mobileLabel: `${titleById[edge.from]} → ${titleById[edge.to]}：${edge.label}`
      };
    });
    return {
      scope: graph.scope,
      macros: graph.macro_loops.map((macro) => ({
        ...macro,
        visible: macroVisibility[macro.id] !== false
      })),
      nodes,
      segments,
      edges,
      relationEdges: edges.filter((edge) => edge.kind !== "primary")
    };
  }

  function globalLoopPartsMarkup(parts) {
    return parts.map((part) => `
      <div class="global-loop-part loop-part-${part.key}"
        data-loop-part="${escapeHtml(part.key)}">
        <strong>${escapeHtml(part.label)}</strong>
        ${part.values.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}
      </div>
    `).join('<span class="global-loop-part-arrow" aria-hidden="true">→</span>');
  }

  function microLoopMarkup(node) {
    const disabled = node.disabled ? ' aria-disabled="true"' : ' aria-disabled="false"';
    const statusClass = node.status === "pending_confirmation" ? " pending-confirmation" : "";
    return `
      <article class="global-flow-node micro-loop-card${statusClass}${node.dimmed ? " macro-loop-dimmed" : ""}"
        data-loop-node="${escapeHtml(node.id)}" data-loop-slice="${node.primarySlice}"
        role="button" tabindex="${node.disabled ? -1 : 0}"${disabled}>
        <header>
          <span class="micro-loop-index">小 LOOP</span>
          <h3>${escapeHtml(node.title)}</h3>
          <small>${escapeHtml(node.timeLabel)}</small>
        </header>
        <p>${escapeHtml(node.summary)}</p>
        <div class="micro-loop-parts">${globalLoopPartsMarkup(node.parts)}</div>
      </article>`;
  }

  function linearLoopNodeMarkup(node) {
    const disabled = node.disabled ? ' aria-disabled="true"' : ' aria-disabled="false"';
    const statusClass = node.status === "pending_confirmation" ? " pending-confirmation" : "";
    return `
      <article class="global-flow-node global-linear-node node-${escapeHtml(node.type)}${statusClass}"
        data-loop-node="${escapeHtml(node.id)}" data-loop-slice="${node.primarySlice}"
        role="button" tabindex="${node.disabled ? -1 : 0}"${disabled}>
        <span>${escapeHtml(node.type === "outside_exit" ? "范围外" : "流程节点")}</span>
        <h3>${escapeHtml(node.title)}</h3>
        <p>${escapeHtml(node.summary)}</p>
        <small>${escapeHtml(node.timeLabel)}</small>
      </article>`;
  }

  function hierarchicalLoopsMarkup(model) {
    const edgeMarkup = model.edges.map((edge) => `
      <span class="global-loop-edge edge-${escapeHtml(edge.kind)}${edge.dimmed ? " macro-relation-dimmed" : ""}"
        data-edge-from="${escapeHtml(edge.from)}"
        data-edge-to="${escapeHtml(edge.to)}">${escapeHtml(edge.mobileLabel)}</span>
    `).join("");
    const nodeById = Object.fromEntries(model.nodes.map((node) => [node.id, node]));
    const segmentByFirstNode = Object.fromEntries(
      model.segments.map((segment) => [segment.nodeIds[0], segment])
    );
    const consumed = new Set();
    const nodeMarkup = model.nodes.map((node) => {
      if (consumed.has(node.id)) return "";
      const segment = segmentByFirstNode[node.id];
      if (!segment) return linearLoopNodeMarkup(node);
      segment.nodeIds.forEach((nodeId) => consumed.add(nodeId));
      const accent = segment.macro.accent.replaceAll("_", "-");
      return `
        <section class="macro-loop-segment macro-segment-${escapeHtml(accent)}${segment.dimmed ? " macro-loop-dimmed" : ""}"
          data-macro-segment="${escapeHtml(segment.id)}">
          <header class="macro-segment-header">
            <strong>${escapeHtml(segment.macro.title)}</strong>
            <span>${escapeHtml(segment.macro.summary)}</span>
          </header>
          <div class="macro-segment-nodes">
            ${segment.nodeIds.map((nodeId) => microLoopMarkup(nodeById[nodeId])).join("")}
          </div>
        </section>`;
    }).join("");
    return `<div class="global-loop-nodes">${nodeMarkup}</div><div class="global-loop-edge-labels">${edgeMarkup}</div>`;
  }

  function hierarchicalLoopConnectorSvg(model, rectById, width, height) {
    const paths = model.relationEdges.map((edge) => {
      const sourceNode = rectById[edge.from];
      const targetNode = rectById[edge.to];
      const source = edge.kind === "macro_return"
        ? sourceNode?.next || sourceNode?.card
        : edge.kind === "cross_macro"
          ? sourceNode?.reward || sourceNode?.card
          : sourceNode?.card;
      const target = targetNode?.motivation || targetNode?.card;
      if (!source || !target) return "";
      let path;
      if (edge.kind === "macro_return") {
        const startX = source.x + source.width;
        const startY = source.y + source.height / 2;
        const endX = target.x + target.width;
        const endY = target.y + target.height / 2;
        const outerX = Math.min(width - 8, Math.max(startX, endX) + 28);
        path = `M ${startX} ${startY} C ${outerX} ${startY}, ${outerX} ${endY}, ${endX} ${endY}`;
      } else {
        const startX = source.x + source.width;
        const startY = source.y + source.height / 2;
        const endX = target.x;
        const endY = target.y + target.height / 2;
        const middleX = startX + (endX - startX) / 2;
        path = `M ${startX} ${startY} C ${middleX} ${startY}, ${middleX} ${endY}, ${endX} ${endY}`;
      }
      const macroClass = edge.kind === "macro_return" && edge.fromMacroId
        ? ` macro-edge-${escapeHtml(edge.fromMacroId.replaceAll("_", "-"))}`
        : "";
      const dimmedClass = edge.dimmed ? " macro-relation-dimmed" : "";
      return `<path class="global-loop-connector edge-${escapeHtml(edge.kind)}${macroClass}${dimmedClass}" d="${path}" marker-end="url(#global-loop-arrow)"/>`;
    }).join("");
    return `<svg class="global-loop-connectors" viewBox="0 0 ${width} ${height}" aria-hidden="true">
      <defs><marker id="global-loop-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="context-stroke"/></marker></defs>
      ${paths}
    </svg>`;
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      adjacentVisibleIndex,
      aggregateStages,
      classifyHighlights,
      computeTimelineLayout,
      curveSliceInteractionState,
      curveSliceBands,
      curveTooltipPlacement,
      createLightboxController,
      defaultGlobalCurveVisibility,
      detailHtml,
      detailViewModel,
      dimensionTabs,
      encodeAssetPath,
      experienceTrendSummaryMarkup,
      firstVisibleIndexInStage,
      formatTime,
      globalCurvesGuideMarkup,
      globalCurvesLegendMarkup,
      globalCurvesSvgMarkup,
      globalCurvesTooltipMarkup,
      globalCurvesViewModel,
      defaultMacroLoopVisibility,
      globalLoopInteractionState,
      hierarchicalLoopConnectorSvg,
      hierarchicalLoopsMarkup,
      hierarchicalLoopsViewModel,
      loopFamilyStatistics,
      loopFamilyStatisticsMarkup,
      macroLoopLegendMarkup,
      macroLoopSegments,
      relatedLoopNavigationMarkup,
      relatedMicroLoops,
      datasetSwitchTarget,
      normalizeDatasetManifest,
      resolveAnalysisDataPath,
      resolveCurrentDatasetId,
      showAllMacroLoops,
      updateMacroLoopVisibility,
      adjacentGalleryIndex,
      galleryHtml,
      galleryViewModel,
      imageMarkupPure,
      linearRegressionTrend,
      stageAverageExperienceObservations,
      lightboxViewModel,
      loadInitialData,
      restoreGalleryFocus,
      selectedIndexForVisible,
      shouldDismissEmotionTooltip,
      timelineMilestoneMarkup,
      timelineKeyDirection,
      updateGlobalCurveVisibility
    };
    return;
  }

  function highlightBadges(slice) {
    return classifyHighlights(slice).map((label) => {
      const text = label === "flow-high" ? "心流" : label === "narrative-low" ? "低谷" : "高潮";
      return `<i class="node-tag ${label}">${text}</i>`;
    }).join("");
  }

  function renderEmotionCurve() {
    try {
      const curveContainer = byId("emotion-curve-svg");
      const activeCurveSlice = document.activeElement?.matches?.(
        ".curve-slice-hit-zone"
      )
        ? Number(document.activeElement.dataset.curveSlice)
        : null;
      const width = Math.round(curveContainer.clientWidth) || 1000;
      const height = Math.round(curveContainer.clientHeight) || 360;
      state.curveSize = `${width}x${height}`;
      state.curveModel = globalCurvesViewModel(state.data, width, height);
      curveContainer.innerHTML = globalCurvesSvgMarkup(
        state.curveModel,
        state.curveVisibility
      );
      byId("emotion-curve-legend").innerHTML = globalCurvesLegendMarkup(
        state.curveVisibility
      );
      byId("emotion-algorithm-content").innerHTML = globalCurvesGuideMarkup();
      if (Number.isInteger(activeCurveSlice)) {
        curveContainer.querySelector(
          `[data-curve-slice="${activeCurveSlice}"]`
        )?.focus();
      }
      const trend = state.curveModel.trendSummary;
      byId("experience-trend-summary").innerHTML =
        experienceTrendSummaryMarkup(trend);
      byId("emotion-curve-error").hidden = true;
    } catch (error) {
      state.curveModel = null;
      byId("emotion-curve-svg").innerHTML = "";
      byId("emotion-curve-error").textContent = `情绪曲线加载失败：${error.message}`;
      byId("emotion-curve-error").hidden = false;
    }
  }

  function hideEmotionTooltip() {
    byId("emotion-curve-tooltip").hidden = true;
  }

  function showEmotionTooltip(target) {
    if (!state.curveModel) return;
    const index = Number(target.dataset.curveSlice);
    const point = state.curveModel.points[index];
    if (!point) return;
    const tooltip = byId("emotion-curve-tooltip");
    tooltip.innerHTML = globalCurvesTooltipMarkup(point);
    tooltip.hidden = false;
    const canvas = tooltip.parentElement;
    const placement = curveTooltipPlacement(
      point,
      state.curveModel,
      canvas.clientWidth,
      tooltip.offsetWidth
    );
    tooltip.style.left = `${placement.leftPx}px`;
    tooltip.style.top = `${placement.topPercent}%`;
    tooltip.classList.toggle("below", placement.below);
  }

  function renderGlobalLoopConnectors() {
    const canvas = byId("global-loop-canvas");
    const existing = canvas.querySelector(".global-loop-connectors");
    if (existing) existing.remove();
    if (!state.loopModel || window.matchMedia("(max-width: 720px)").matches) return;
    const canvasRect = canvas.getBoundingClientRect();
    const rectById = {};
    canvas.querySelectorAll("[data-loop-node]").forEach((node) => {
      const localRect = (element) => {
        if (!element) return null;
        const rect = element.getBoundingClientRect();
        return {
          x: rect.left - canvasRect.left,
          y: rect.top - canvasRect.top,
          width: rect.width,
          height: rect.height
        };
      };
      rectById[node.dataset.loopNode] = {
        card: localRect(node),
        motivation: localRect(node.querySelector('[data-loop-part="motivation"]')),
        reward: localRect(node.querySelector('[data-loop-part="reward"]')),
        next: localRect(node.querySelector('[data-loop-part="next"]'))
      };
    });
    canvas.insertAdjacentHTML(
      "afterbegin",
      hierarchicalLoopConnectorSvg(
        state.loopModel,
        rectById,
        Math.max(1, canvas.clientWidth),
        Math.max(1, canvas.scrollHeight)
      )
    );
  }

  function renderGlobalLoops() {
    const canvas = byId("global-loop-canvas");
    const error = byId("global-loop-error");
    try {
      state.loopModel = hierarchicalLoopsViewModel(
        state.data,
        state.visible,
        state.macroLoopVisibility
      );
      byId("global-loop-legend").innerHTML = macroLoopLegendMarkup(
        state.loopModel.macros
      );
      byId("global-loop-statistics").innerHTML = loopFamilyStatisticsMarkup(
        loopFamilyStatistics(state.data.global_loops)
      );
      canvas.innerHTML = hierarchicalLoopsMarkup(state.loopModel);
      error.hidden = true;
      requestAnimationFrame(renderGlobalLoopConnectors);
    } catch (renderError) {
      state.loopModel = null;
      canvas.innerHTML = "";
      byId("global-loop-statistics").innerHTML = "";
      error.textContent = `全局 LOOP 流程加载失败：${renderError.message}`;
      error.hidden = false;
    }
    renderRelatedLoopNavigation();
  }

  function renderRelatedLoopNavigation() {
    const container = byId("related-loop-navigation");
    if (!state.data || state.selectedIndex < 0 || !state.loopModel) {
      container.innerHTML = relatedLoopNavigationMarkup([]);
      return;
    }
    container.innerHTML = relatedLoopNavigationMarkup(
      relatedMicroLoops(
        state.loopModel.nodes,
        state.selectedIndex,
        state.visible
      )
    );
  }

  function focusLoopNode(nodeId) {
    const target = [...document.querySelectorAll("[data-loop-node]")].find(
      (node) => node.dataset.loopNode === nodeId
    );
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.remove("loop-location-pulse");
    requestAnimationFrame(() => target.classList.add("loop-location-pulse"));
    window.setTimeout(
      () => target.classList.remove("loop-location-pulse"),
      1400
    );
  }

  function renderOverview(data) {
    const duration = data.video.duration_seconds;
    const stages = aggregateStages(data.slices);
    const sliceLengths = [...new Set(data.slices.map((slice) => slice.end - slice.start))];
    const videoName = data.video.path.replace(/\\/g, "/").split("/").pop();
    byId("game-title").textContent = videoName.replace(/\.[^.]+$/, "") || "游戏前期体验拆解";
    byId("video-overview").textContent = `视频：${videoName} · ${formatTime(duration)} · ${data.slices.length} 个观察时间片`;
    byId("summary-cards").innerHTML = [
      ["总时长", formatTime(duration)],
      ["阶段", stages.length],
      ["时间片", data.slices.length]
    ].map(([label, value]) => `<div class="summary-card"><strong>${escapeHtml(value)}</strong><span>${label}</span></div>`).join("");
    byId("time-granularity").textContent = `粒度：${sliceLengths.map((length) => `${length} 秒`).join(" / ")}`;
    byId("result-count").textContent = `${data.slices.length} 个时间片`;
    byId("stage-summary").innerHTML = stages.map((stage) =>
      `<button type="button" data-slice="${stage.firstIndex}"><strong>${escapeHtml(stage.name)}</strong><span>${formatTime(stage.start)}–${formatTime(stage.end)}</span></button>`
    ).join("");
  }

  function renderTimeline(data) {
    const duration = data.video.duration_seconds;
    const layout = computeTimelineLayout(duration, data.slices);
    const tickSeconds = duration > 60 * 60 ? 10 * 60 : duration > 30 * 60 ? 5 * 60 : 60;
    const markCount = Math.ceil(duration / tickSeconds);
    byId("timeline-axis").innerHTML = Array.from({ length: markCount + 1 }, (_, index) => {
      const second = Math.min(duration, index * tickSeconds);
      return `<span class="axis-mark" style="left:${second / duration * 100}%">${formatTime(second)}</span>`;
    }).join("");
    const overviewTrack = byId("overview-track");
    const milestones = timelineMilestoneMarkup(
      data.timeline_milestones || [],
      duration
    );
    overviewTrack.innerHTML = milestones + data.slices.map((slice, index) => {
      const geometry = layout.nodes[index];
      const highlights = classifyHighlights(slice);
      const wideEnough = geometry.width >= 2.5;
      return `<button class="timeline-node ${highlights.join(" ")}" data-slice="${index}" style="left:${geometry.left}%;width:${geometry.width}%" type="button" title="${escapeHtml(`${formatTime(slice.start)}–${formatTime(slice.end)} ${slice.stage_range.name}`)}" aria-label="${escapeHtml(`${formatTime(slice.start)} 至 ${formatTime(slice.end)}，${slice.stage_range.name}`)}">
        ${wideEnough ? `<span>${formatTime(slice.start)}</span>` : ""}
        <span class="node-tags">${highlightBadges(slice)}</span>
      </button>`;
    }).join("");
    overviewTrack.onclick = (event) => {
      const button = event.target.closest("[data-slice]");
      if (button) selectSlice(Number(button.dataset.slice));
    };
  }

  function renderSelected() {
    function renderCurveSliceStates() {
      document.querySelectorAll(".curve-slice-hit-zone").forEach((point) => {
        const index = Number(point.dataset.curveSlice);
        const interaction = curveSliceInteractionState(
          index, state.selectedIndex, state.visible
        );
        point.classList.toggle("selected", interaction.selected);
        point.classList.toggle("filtered-out", interaction.filteredOut);
        point.setAttribute(
          "aria-current", interaction.selected ? "true" : "false"
        );
        point.setAttribute(
          "aria-disabled", interaction.disabled ? "true" : "false"
        );
      });
    }
    renderRelatedLoopNavigation();
    if (state.selectedIndex < 0) {
      byId("detail-time").textContent = "筛选结果为空";
      byId("detail-title").textContent = "没有匹配的时间片";
      byId("detail-content").innerHTML = "";
      byId("dimension-tabs").innerHTML = "";
      byId("dimension-description").innerHTML = "<p>请调整上方筛选条件。</p>";
      byId("previous-slice").disabled = true;
      byId("next-slice").disabled = true;
      document.querySelectorAll(".timeline-node").forEach((button) => {
        button.classList.remove("selected");
        button.setAttribute("aria-current", "false");
      });
      renderCurveSliceStates();
      return;
    }
    const slice = state.data.slices[state.selectedIndex];
    const detail = detailViewModel(slice, state.activeDimension);
    state.activeDimension = detail.dimension;
    byId("detail-time").textContent = `${formatTime(slice.start)}–${formatTime(slice.end)} · 时间片 ${state.selectedIndex + 1}/${state.data.slices.length}`;
    byId("detail-title").textContent = slice.stage_range.name;
    byId("detail-content").innerHTML = `
      ${galleryHtml(detail.screenshots, state.galleryIndex)}
      <aside class="slice-meta">
        <div class="confidence"><span>置信度</span><strong>${detail.confidence}%</strong></div>
        ${detail.questions.length ? `<section class="questions"><h3>待确认项</h3><ul>${detail.questions.map((question) => `<li>${escapeHtml(question)}</li>`).join("")}</ul></section>` : ""}
      </aside>`;
    byId("dimension-tabs").innerHTML = tabsMarkup(detail.tabs);
    byId("dimension-description").innerHTML = `<p>${escapeHtml(detail.description)}</p>`;
    document.querySelectorAll(".timeline-node").forEach((button, index) => {
      const selected = index === state.selectedIndex;
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-current", selected ? "true" : "false");
    });
    renderCurveSliceStates();
    byId("previous-slice").disabled = adjacentVisibleIndex(state.selectedIndex, -1, state.visible) === state.selectedIndex;
    byId("next-slice").disabled = adjacentVisibleIndex(state.selectedIndex, 1, state.visible) === state.selectedIndex;
  }

  function selectSlice(index) {
    if (!state.visible[index]) return;
    state.selectedIndex = index;
    state.galleryIndex = 0;
    const current = state.data.slices[index];
    if (!String(current.dimensions[state.activeDimension]?.fact || "").trim()) {
      state.activeDimension = "";
    }
    renderSelected();
    byId("detail-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function initialize(data) {
    if (!data || !data.video || !Array.isArray(data.slices) || !data.slices.length) {
      throw new Error("data.json 内容为空或格式不正确");
    }
    state.data = data;
    state.visible = data.slices.map(() => true);
    state.selectedIndex = 0;
    state.activeDimension = "";
    state.galleryIndex = 0;
    state.curveVisibility = defaultGlobalCurveVisibility();
    state.macroLoopVisibility = defaultMacroLoopVisibility(
      data.global_loops?.macro_loops || []
    );
    renderOverview(data);
    renderEmotionCurve();
    renderTimeline(data);
    renderSelected();
    renderGlobalLoops();
    byId("load-error").hidden = true;
  }

  function showLoadError(error) {
    byId("load-error").hidden = false;
    byId("video-overview").textContent = `读取失败：${error.message}`;
  }

  function renderDatasetSwitch(payload, currentId) {
    const select = byId("dataset-switch");
    const datasets = normalizeDatasetManifest(payload, currentId);
    const options = datasets.map((dataset) => {
      const option = document.createElement("option");
      option.value = dataset.id;
      option.textContent = dataset.label;
      return option;
    });
    select.replaceChildren(...options);
    if (datasets.some((dataset) => dataset.id === currentId)) {
      select.value = currentId;
    }
    select.disabled = datasets.length <= 1;
  }

  byId("emotion-curve-legend").addEventListener("click", (event) => {
    const seriesButton = event.target.closest("[data-curve-series-toggle]");
    const actionButton = event.target.closest("[data-curve-action]");
    if (seriesButton) {
      state.curveVisibility = updateGlobalCurveVisibility(state.curveVisibility, {
        type: "toggle",
        series: seriesButton.dataset.curveSeriesToggle
      });
    } else if (actionButton) {
      state.curveVisibility = updateGlobalCurveVisibility(state.curveVisibility, {
        type: actionButton.dataset.curveAction
      });
    } else {
      return;
    }
    renderEmotionCurve();
    renderSelected();
  });
  byId("emotion-curve-svg").addEventListener("click", (event) => {
    const point = event.target.closest("[data-curve-slice]");
    if (!point) return;
    const index = Number(point.dataset.curveSlice);
    if (state.visible[index]) selectSlice(index);
  });
  byId("emotion-curve-svg").addEventListener("pointerover", (event) => {
    const point = event.target.closest("[data-curve-slice]");
    if (point) showEmotionTooltip(point);
  });
  byId("emotion-curve-svg").addEventListener("focusin", (event) => {
    const point = event.target.closest("[data-curve-slice]");
    if (point) showEmotionTooltip(point);
  });
  byId("emotion-curve-svg").addEventListener("pointerleave", hideEmotionTooltip);
  byId("emotion-curve-svg").addEventListener("focusout", hideEmotionTooltip);
  byId("emotion-curve-svg").addEventListener("keydown", (event) => {
    const point = event.target.closest("[data-curve-slice]");
    if (!point || !["Enter", " "].includes(event.key)) return;
    event.preventDefault();
    const index = Number(point.dataset.curveSlice);
    if (state.visible[index]) selectSlice(index);
  });
  byId("global-loop-legend").addEventListener("click", (event) => {
    const button = event.target.closest("[data-macro-loop-toggle]");
    const action = event.target.closest("[data-macro-loop-action]");
    if (button) {
      state.macroLoopVisibility = updateMacroLoopVisibility(
        state.macroLoopVisibility,
        button.dataset.macroLoopToggle
      );
    } else if (action?.dataset.macroLoopAction === "show-all") {
      state.macroLoopVisibility = showAllMacroLoops(state.macroLoopVisibility);
    } else return;
    renderGlobalLoops();
  });
  byId("related-loop-navigation").addEventListener("click", (event) => {
    const button = event.target.closest("[data-related-loop]");
    if (!button || button.disabled) return;
    focusLoopNode(button.dataset.relatedLoop);
  });
  byId("global-loop-canvas").addEventListener("click", (event) => {
    const node = event.target.closest("[data-loop-node]");
    if (!node || node.getAttribute("aria-disabled") === "true") return;
    selectSlice(Number(node.dataset.loopSlice));
  });
  byId("global-loop-canvas").addEventListener("keydown", (event) => {
    const node = event.target.closest("[data-loop-node]");
    if (!node || !["Enter", " "].includes(event.key)
      || node.getAttribute("aria-disabled") === "true") return;
    event.preventDefault();
    selectSlice(Number(node.dataset.loopSlice));
  });
  byId("stage-summary").addEventListener("click", (event) => {
    const button = event.target.closest("[data-slice]");
    if (!button) return;
    const stageName = state.data.slices[Number(button.dataset.slice)].stage_range.name;
    const index = firstVisibleIndexInStage(stageName, state.data.slices, state.visible);
    if (index >= 0) selectSlice(index);
  });
  byId("dimension-tabs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-dimension]");
    if (!button || button.disabled) return;
    state.activeDimension = button.dataset.dimension;
    renderSelected();
  });
  byId("detail-content").addEventListener("click", (event) => {
    const indexed = event.target.closest("[data-gallery-index]");
    const directed = event.target.closest("[data-gallery-direction]");
    if (indexed) {
      state.galleryIndex = Number(indexed.dataset.galleryIndex);
      renderSelected();
    } else if (directed) {
      const count = detailViewModel(state.data.slices[state.selectedIndex]).screenshots.length;
      state.galleryIndex = adjacentGalleryIndex(
        state.galleryIndex,
        Number(directed.dataset.galleryDirection),
        count
      );
      renderSelected();
    }
  });
  byId("previous-slice").addEventListener("click", () =>
    selectSlice(adjacentVisibleIndex(state.selectedIndex, -1, state.visible))
  );
  byId("next-slice").addEventListener("click", () =>
    selectSlice(adjacentVisibleIndex(state.selectedIndex, 1, state.visible))
  );
  document.addEventListener("keydown", (event) => {
    if (shouldDismissEmotionTooltip(event) && !byId("emotion-curve-tooltip").hidden) {
      hideEmotionTooltip();
    }
    const direction = timelineKeyDirection(event);
    if (!direction || !state.data || state.selectedIndex < 0 || byId("lightbox").open) return;
    event.preventDefault();
    if (event.target.closest?.(".gallery")) {
      const count = detailViewModel(state.data.slices[state.selectedIndex]).screenshots.length;
      state.galleryIndex = adjacentGalleryIndex(state.galleryIndex, direction, count);
      renderSelected();
      restoreGalleryFocus(byId("detail-content"));
      return;
    }
    selectSlice(adjacentVisibleIndex(state.selectedIndex, direction, state.visible));
  });
  lightboxController = createLightboxController({
    lightbox: byId("lightbox"),
    lightboxClose: byId("close-lightbox"),
    lightboxImage: byId("lightbox-image"),
    lightboxCaption: byId("lightbox-caption"),
    documentRef: document
  });
  byId("detail-content").addEventListener("click", lightboxController.activateImage);
  byId("detail-content").addEventListener("keydown", lightboxController.activateImage);
  let swipeStartX = null;
  byId("detail-content").addEventListener("pointerdown", (event) => {
    if (event.target.closest(".gallery")) swipeStartX = event.clientX;
  });
  byId("detail-content").addEventListener("pointerup", (event) => {
    if (swipeStartX === null || !event.target.closest(".gallery")) return;
    const distance = event.clientX - swipeStartX;
    swipeStartX = null;
    if (Math.abs(distance) < 45) return;
    const count = detailViewModel(state.data.slices[state.selectedIndex]).screenshots.length;
    state.galleryIndex = adjacentGalleryIndex(state.galleryIndex, distance > 0 ? -1 : 1, count);
    renderSelected();
  });
  byId("lightbox-image").addEventListener("error", () => {
    byId("lightbox-image").hidden = true;
    byId("lightbox-caption").textContent = "图片加载失败";
  });
  byId("data-file").addEventListener("change", async (event) => {
    try {
      initialize(JSON.parse(await event.target.files[0].text()));
    } catch (error) {
      showLoadError(error);
    }
  });
  if (typeof ResizeObserver !== "undefined") {
    const curveContainer = byId("emotion-curve-svg");
    const curveResizeObserver = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect || !state.data) return;
      const nextSize = `${Math.round(rect.width)}x${Math.round(rect.height)}`;
      if (nextSize !== state.curveSize) {
        renderEmotionCurve();
        renderSelected();
      }
    });
    curveResizeObserver.observe(curveContainer);
    const loopContainer = byId("global-loop-canvas");
    const loopResizeObserver = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect || !state.data) return;
      const nextSize = `${Math.round(rect.width)}x${Math.round(rect.height)}`;
      if (nextSize !== state.loopSize) {
        state.loopSize = nextSize;
        renderGlobalLoopConnectors();
      }
    });
    loopResizeObserver.observe(loopContainer);
  }

  const configuredDataFile = document
    .querySelector('meta[name="analysis-data-file"]')
    ?.getAttribute("content") || "data.json";
  const initialDataFile = resolveAnalysisDataPath(
    window.location.search,
    configuredDataFile
  );
  const currentDatasetId = resolveCurrentDatasetId(
    window.location.search,
    configuredDataFile
  );
  renderDatasetSwitch({ datasets: [] }, currentDatasetId);
  byId("dataset-switch").addEventListener("change", (event) => {
    const target = datasetSwitchTarget(window.location.href, event.target.value);
    if (target && target !== window.location.href) window.location.assign(target);
  });
  fetch("data/datasets.json", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`data/datasets.json 返回 ${response.status}`);
      return response.json();
    })
    .then((manifest) => renderDatasetSwitch(manifest, currentDatasetId))
    .catch(() => renderDatasetSwitch({ datasets: [] }, currentDatasetId));
  loadInitialData(
    () => fetch(initialDataFile, { cache: "no-store" }).then((response) => {
      if (!response.ok) throw new Error(`${initialDataFile} 返回 ${response.status}`);
      return response.json();
    }),
    initialize,
    showLoadError
  );
})();
