// GENERATED — do not edit by hand.
//
// Regenerate with:  python scripts/generate_dart_models.py
// Source: the service's own OpenAPI schema, so these cannot drift from the API.

// ignore_for_file: unnecessary_this, prefer_if_null_operators

/// Parses the API's ISO-8601 timestamps, which are always UTC on the wire.
DateTime? _date(Object? value) =>
    value == null ? null : DateTime.parse(value as String).toUtc();

double? _double(Object? value) =>
    value == null ? null : (value as num).toDouble();

int? _int(Object? value) => value == null ? null : (value as num).toInt();

/// `AchievementResponse` from the API schema.
class AchievementResponse {
  final String code;
  final String name;
  final String description;
  final String category;
  final String rarity;
  final String icon;
  final int xpAward;
  final double target;
  final bool requiresPhoto;
  final double current;
  final double percent;
  final bool earned;
  final DateTime? earnedAt;

  const AchievementResponse({
    required this.code,
    required this.name,
    required this.description,
    required this.category,
    required this.rarity,
    required this.icon,
    required this.xpAward,
    required this.target,
    required this.requiresPhoto,
    required this.current,
    required this.percent,
    required this.earned,
    this.earnedAt,
  });

  factory AchievementResponse.fromJson(Map<String, dynamic> json) =>
      AchievementResponse(
        code: (json['code'] as String?)!,
        name: (json['name'] as String?)!,
        description: (json['description'] as String?)!,
        category: (json['category'] as String?)!,
        rarity: (json['rarity'] as String?)!,
        icon: (json['icon'] as String?)!,
        xpAward: (_int(json['xp_award']))!,
        target: (_double(json['target']))!,
        requiresPhoto: (json['requires_photo'] as bool?)!,
        current: (_double(json['current']))!,
        percent: (_double(json['percent']))!,
        earned: (json['earned'] as bool?)!,
        earnedAt: _date(json['earned_at']),
      );
}

/// A running session with everything a countdown needs.
class ActiveProofSession {
  final String id;
  final String? starterId;
  final String? bakeId;
  final String stage;
  final String status;
  final DateTime startedAt;
  final DateTime? actualEndAt;
  final double doughTempC;
  final double? ambientTempC;
  final double starterPct;
  final double? hydrationPct;
  final double targetRisePct;
  final int? plannedDurationMinutes;
  final DateTime predictedEndAt;
  final DateTime windowStartAt;
  final DateTime windowEndAt;
  final double vigourUsed;
  final String? notes;
  final int checkCount;
  final double? latestRisePct;
  final double progressPct;
  final double hoursRemaining;

  const ActiveProofSession({
    required this.id,
    this.starterId,
    this.bakeId,
    required this.stage,
    required this.status,
    required this.startedAt,
    this.actualEndAt,
    required this.doughTempC,
    this.ambientTempC,
    required this.starterPct,
    this.hydrationPct,
    required this.targetRisePct,
    this.plannedDurationMinutes,
    required this.predictedEndAt,
    required this.windowStartAt,
    required this.windowEndAt,
    required this.vigourUsed,
    this.notes,
    required this.checkCount,
    this.latestRisePct,
    required this.progressPct,
    required this.hoursRemaining,
  });

  factory ActiveProofSession.fromJson(Map<String, dynamic> json) =>
      ActiveProofSession(
        id: (json['id'] as String?)!,
        starterId: json['starter_id'] as String?,
        bakeId: json['bake_id'] as String?,
        stage: (json['stage'] as String?)!,
        status: (json['status'] as String?)!,
        startedAt: (_date(json['started_at']))!,
        actualEndAt: _date(json['actual_end_at']),
        doughTempC: (_double(json['dough_temp_c']))!,
        ambientTempC: _double(json['ambient_temp_c']),
        starterPct: (_double(json['starter_pct']))!,
        hydrationPct: _double(json['hydration_pct']),
        targetRisePct: (_double(json['target_rise_pct']))!,
        plannedDurationMinutes: _int(json['planned_duration_minutes']),
        predictedEndAt: (_date(json['predicted_end_at']))!,
        windowStartAt: (_date(json['window_start_at']))!,
        windowEndAt: (_date(json['window_end_at']))!,
        vigourUsed: (_double(json['vigour_used']))!,
        notes: json['notes'] as String?,
        checkCount: (_int(json['check_count']))!,
        latestRisePct: _double(json['latest_rise_pct']),
        progressPct: (_double(json['progress_pct']))!,
        hoursRemaining: (_double(json['hours_remaining']))!,
      );
}

/// `AdminUserRow` from the API schema.
class AdminUserRow {
  final String id;
  final String email;
  final String handle;
  final String displayName;
  final String role;
  final bool isVerified;
  final bool isSuspended;
  final String? suspendedReason;
  final DateTime createdAt;
  final DateTime? lastLoginAt;
  final int publicRecipes;
  final int bakes;

  const AdminUserRow({
    required this.id,
    required this.email,
    required this.handle,
    required this.displayName,
    required this.role,
    required this.isVerified,
    required this.isSuspended,
    this.suspendedReason,
    required this.createdAt,
    this.lastLoginAt,
    required this.publicRecipes,
    required this.bakes,
  });

  factory AdminUserRow.fromJson(Map<String, dynamic> json) => AdminUserRow(
    id: (json['id'] as String?)!,
    email: (json['email'] as String?)!,
    handle: (json['handle'] as String?)!,
    displayName: (json['display_name'] as String?)!,
    role: (json['role'] as String?)!,
    isVerified: (json['is_verified'] as bool?)!,
    isSuspended: (json['is_suspended'] as bool?)!,
    suspendedReason: json['suspended_reason'] as String?,
    createdAt: (_date(json['created_at']))!,
    lastLoginAt: _date(json['last_login_at']),
    publicRecipes: (_int(json['public_recipes']))!,
    bakes: (_int(json['bakes']))!,
  );
}

/// `AwardResponse` from the API schema.
class AwardResponse {
  final String code;
  final String name;
  final String description;
  final String icon;
  final String rarity;
  final int xpAward;

  const AwardResponse({
    required this.code,
    required this.name,
    required this.description,
    required this.icon,
    required this.rarity,
    required this.xpAward,
  });

  factory AwardResponse.fromJson(Map<String, dynamic> json) => AwardResponse(
    code: (json['code'] as String?)!,
    name: (json['name'] as String?)!,
    description: (json['description'] as String?)!,
    icon: (json['icon'] as String?)!,
    rarity: (json['rarity'] as String?)!,
    xpAward: (_int(json['xp_award']))!,
  );
}

/// `BakeCompleteRequest` from the API schema.
class BakeCompleteRequest {
  final DateTime? finishedAt;
  final double? ovenTempC;
  final int? bakeTimeMinutes;
  final String? notes;
  final bool? consumeInventory;

  const BakeCompleteRequest({
    this.finishedAt,
    this.ovenTempC,
    this.bakeTimeMinutes,
    this.notes,
    this.consumeInventory,
  });

  factory BakeCompleteRequest.fromJson(Map<String, dynamic> json) =>
      BakeCompleteRequest(
        finishedAt: _date(json['finished_at']),
        ovenTempC: _double(json['oven_temp_c']),
        bakeTimeMinutes: _int(json['bake_time_minutes']),
        notes: json['notes'] as String?,
        consumeInventory: json['consume_inventory'] as bool?,
      );
}

/// Completion reports what it drew from stock and what it earned.
class BakeCompleteResponse {
  final String id;
  final String? recipeId;
  final String title;
  final String status;
  final DateTime startedAt;
  final DateTime? finishedAt;
  final double? totalFlourG;
  final double? hydrationPct;
  final double? saltPct;
  final double? starterPct;
  final Map<String, dynamic>? flourBlend;
  final int loafCount;
  final double? ovenTempC;
  final int? bakeTimeMinutes;
  final String? vessel;
  final String? scoringPattern;
  final List<Map<String, dynamic>> steps;
  final String? notes;
  final double? flourCost;
  final double? flourCostPerLoaf;
  final RatingResponse? rating;
  final int photoCount;
  final ConsumptionResponse? inventory;
  final int? xpGained;
  final List<AwardResponse>? awards;

  const BakeCompleteResponse({
    required this.id,
    this.recipeId,
    required this.title,
    required this.status,
    required this.startedAt,
    this.finishedAt,
    this.totalFlourG,
    this.hydrationPct,
    this.saltPct,
    this.starterPct,
    this.flourBlend,
    required this.loafCount,
    this.ovenTempC,
    this.bakeTimeMinutes,
    this.vessel,
    this.scoringPattern,
    required this.steps,
    this.notes,
    this.flourCost,
    this.flourCostPerLoaf,
    this.rating,
    required this.photoCount,
    this.inventory,
    this.xpGained,
    this.awards,
  });

  factory BakeCompleteResponse.fromJson(
    Map<String, dynamic> json,
  ) => BakeCompleteResponse(
    id: (json['id'] as String?)!,
    recipeId: json['recipe_id'] as String?,
    title: (json['title'] as String?)!,
    status: (json['status'] as String?)!,
    startedAt: (_date(json['started_at']))!,
    finishedAt: _date(json['finished_at']),
    totalFlourG: _double(json['total_flour_g']),
    hydrationPct: _double(json['hydration_pct']),
    saltPct: _double(json['salt_pct']),
    starterPct: _double(json['starter_pct']),
    flourBlend: json['flour_blend'] == null
        ? null
        : Map<String, dynamic>.from(json['flour_blend'] as Map),
    loafCount: (_int(json['loaf_count']))!,
    ovenTempC: _double(json['oven_temp_c']),
    bakeTimeMinutes: _int(json['bake_time_minutes']),
    vessel: json['vessel'] as String?,
    scoringPattern: json['scoring_pattern'] as String?,
    steps: (json['steps'] == null
        ? null
        : (json['steps'] as List)
              .map(
                (e) =>
                    (e == null ? null : Map<String, dynamic>.from(e as Map))!,
              )
              .toList()
              .cast<Map<String, dynamic>>())!,
    notes: json['notes'] as String?,
    flourCost: _double(json['flour_cost']),
    flourCostPerLoaf: _double(json['flour_cost_per_loaf']),
    rating: json['rating'] == null
        ? null
        : RatingResponse.fromJson(json['rating'] as Map<String, dynamic>),
    photoCount: (_int(json['photo_count']))!,
    inventory: json['inventory'] == null
        ? null
        : ConsumptionResponse.fromJson(
            json['inventory'] as Map<String, dynamic>,
          ),
    xpGained: _int(json['xp_gained']),
    awards: json['awards'] == null
        ? null
        : (json['awards'] as List)
              .map(
                (e) => (e == null
                    ? null
                    : AwardResponse.fromJson(e as Map<String, dynamic>))!,
              )
              .toList()
              .cast<AwardResponse>(),
  );
}

/// `BakeCreate` from the API schema.
class BakeCreate {
  final String title;
  final String? recipeId;
  final DateTime? startedAt;
  final double? totalFlourG;
  final double? hydrationPct;
  final double? saltPct;
  final double? starterPct;
  final Map<String, dynamic>? flourBlend;
  final int? loafCount;
  final double? ovenTempC;
  final int? bakeTimeMinutes;
  final String? vessel;
  final String? scoringPattern;
  final List<Map<String, dynamic>>? steps;
  final String? notes;

  const BakeCreate({
    required this.title,
    this.recipeId,
    this.startedAt,
    this.totalFlourG,
    this.hydrationPct,
    this.saltPct,
    this.starterPct,
    this.flourBlend,
    this.loafCount,
    this.ovenTempC,
    this.bakeTimeMinutes,
    this.vessel,
    this.scoringPattern,
    this.steps,
    this.notes,
  });

  factory BakeCreate.fromJson(Map<String, dynamic> json) => BakeCreate(
    title: (json['title'] as String?)!,
    recipeId: json['recipe_id'] as String?,
    startedAt: _date(json['started_at']),
    totalFlourG: _double(json['total_flour_g']),
    hydrationPct: _double(json['hydration_pct']),
    saltPct: _double(json['salt_pct']),
    starterPct: _double(json['starter_pct']),
    flourBlend: json['flour_blend'] == null
        ? null
        : Map<String, dynamic>.from(json['flour_blend'] as Map),
    loafCount: _int(json['loaf_count']),
    ovenTempC: _double(json['oven_temp_c']),
    bakeTimeMinutes: _int(json['bake_time_minutes']),
    vessel: json['vessel'] as String?,
    scoringPattern: json['scoring_pattern'] as String?,
    steps: json['steps'] == null
        ? null
        : (json['steps'] as List)
              .map(
                (e) =>
                    (e == null ? null : Map<String, dynamic>.from(e as Map))!,
              )
              .toList()
              .cast<Map<String, dynamic>>(),
    notes: json['notes'] as String?,
  );
}

/// `BakeResponse` from the API schema.
class BakeResponse {
  final String id;
  final String? recipeId;
  final String title;
  final String status;
  final DateTime startedAt;
  final DateTime? finishedAt;
  final double? totalFlourG;
  final double? hydrationPct;
  final double? saltPct;
  final double? starterPct;
  final Map<String, dynamic>? flourBlend;
  final int loafCount;
  final double? ovenTempC;
  final int? bakeTimeMinutes;
  final String? vessel;
  final String? scoringPattern;
  final List<Map<String, dynamic>> steps;
  final String? notes;
  final double? flourCost;
  final double? flourCostPerLoaf;
  final RatingResponse? rating;
  final int photoCount;

  const BakeResponse({
    required this.id,
    this.recipeId,
    required this.title,
    required this.status,
    required this.startedAt,
    this.finishedAt,
    this.totalFlourG,
    this.hydrationPct,
    this.saltPct,
    this.starterPct,
    this.flourBlend,
    required this.loafCount,
    this.ovenTempC,
    this.bakeTimeMinutes,
    this.vessel,
    this.scoringPattern,
    required this.steps,
    this.notes,
    this.flourCost,
    this.flourCostPerLoaf,
    this.rating,
    required this.photoCount,
  });

  factory BakeResponse.fromJson(Map<String, dynamic> json) => BakeResponse(
    id: (json['id'] as String?)!,
    recipeId: json['recipe_id'] as String?,
    title: (json['title'] as String?)!,
    status: (json['status'] as String?)!,
    startedAt: (_date(json['started_at']))!,
    finishedAt: _date(json['finished_at']),
    totalFlourG: _double(json['total_flour_g']),
    hydrationPct: _double(json['hydration_pct']),
    saltPct: _double(json['salt_pct']),
    starterPct: _double(json['starter_pct']),
    flourBlend: json['flour_blend'] == null
        ? null
        : Map<String, dynamic>.from(json['flour_blend'] as Map),
    loafCount: (_int(json['loaf_count']))!,
    ovenTempC: _double(json['oven_temp_c']),
    bakeTimeMinutes: _int(json['bake_time_minutes']),
    vessel: json['vessel'] as String?,
    scoringPattern: json['scoring_pattern'] as String?,
    steps: (json['steps'] == null
        ? null
        : (json['steps'] as List)
              .map(
                (e) =>
                    (e == null ? null : Map<String, dynamic>.from(e as Map))!,
              )
              .toList()
              .cast<Map<String, dynamic>>())!,
    notes: json['notes'] as String?,
    flourCost: _double(json['flour_cost']),
    flourCostPerLoaf: _double(json['flour_cost_per_loaf']),
    rating: json['rating'] == null
        ? null
        : RatingResponse.fromJson(json['rating'] as Map<String, dynamic>),
    photoCount: (_int(json['photo_count']))!,
  );
}

/// `BakeUpdate` from the API schema.
class BakeUpdate {
  final String? title;
  final double? totalFlourG;
  final double? hydrationPct;
  final double? saltPct;
  final double? starterPct;
  final Map<String, dynamic>? flourBlend;
  final int? loafCount;
  final double? ovenTempC;
  final int? bakeTimeMinutes;
  final String? vessel;
  final String? scoringPattern;
  final List<Map<String, dynamic>>? steps;
  final String? notes;

  const BakeUpdate({
    this.title,
    this.totalFlourG,
    this.hydrationPct,
    this.saltPct,
    this.starterPct,
    this.flourBlend,
    this.loafCount,
    this.ovenTempC,
    this.bakeTimeMinutes,
    this.vessel,
    this.scoringPattern,
    this.steps,
    this.notes,
  });

  factory BakeUpdate.fromJson(Map<String, dynamic> json) => BakeUpdate(
    title: json['title'] as String?,
    totalFlourG: _double(json['total_flour_g']),
    hydrationPct: _double(json['hydration_pct']),
    saltPct: _double(json['salt_pct']),
    starterPct: _double(json['starter_pct']),
    flourBlend: json['flour_blend'] == null
        ? null
        : Map<String, dynamic>.from(json['flour_blend'] as Map),
    loafCount: _int(json['loaf_count']),
    ovenTempC: _double(json['oven_temp_c']),
    bakeTimeMinutes: _int(json['bake_time_minutes']),
    vessel: json['vessel'] as String?,
    scoringPattern: json['scoring_pattern'] as String?,
    steps: json['steps'] == null
        ? null
        : (json['steps'] as List)
              .map(
                (e) =>
                    (e == null ? null : Map<String, dynamic>.from(e as Map))!,
              )
              .toList()
              .cast<Map<String, dynamic>>(),
    notes: json['notes'] as String?,
  );
}

/// `ChangePasswordRequest` from the API schema.
class ChangePasswordRequest {
  final String currentPassword;
  final String newPassword;

  const ChangePasswordRequest({
    required this.currentPassword,
    required this.newPassword,
  });

  factory ChangePasswordRequest.fromJson(Map<String, dynamic> json) =>
      ChangePasswordRequest(
        currentPassword: (json['current_password'] as String?)!,
        newPassword: (json['new_password'] as String?)!,
      );
}

/// `ChannelResponse` from the API schema.
class ChannelResponse {
  final String id;
  final String kind;
  final String? label;
  final bool isEnabled;
  final int consecutiveFailures;
  final DateTime? lastUsedAt;
  final DateTime createdAt;
  final String target;

  const ChannelResponse({
    required this.id,
    required this.kind,
    this.label,
    required this.isEnabled,
    required this.consecutiveFailures,
    this.lastUsedAt,
    required this.createdAt,
    required this.target,
  });

  factory ChannelResponse.fromJson(Map<String, dynamic> json) =>
      ChannelResponse(
        id: (json['id'] as String?)!,
        kind: (json['kind'] as String?)!,
        label: json['label'] as String?,
        isEnabled: (json['is_enabled'] as bool?)!,
        consecutiveFailures: (_int(json['consecutive_failures']))!,
        lastUsedAt: _date(json['last_used_at']),
        createdAt: (_date(json['created_at']))!,
        target: (json['target'] as String?)!,
      );
}

/// `ConfirmUploadRequest` from the API schema.
class ConfirmUploadRequest {
  final String objectKey;

  const ConfirmUploadRequest({required this.objectKey});

  factory ConfirmUploadRequest.fromJson(Map<String, dynamic> json) =>
      ConfirmUploadRequest(objectKey: (json['object_key'] as String?)!);
}

/// `ConfirmUploadResponse` from the API schema.
class ConfirmUploadResponse {
  final String objectKey;
  final int sizeBytes;
  final String contentType;
  final String url;

  const ConfirmUploadResponse({
    required this.objectKey,
    required this.sizeBytes,
    required this.contentType,
    required this.url,
  });

  factory ConfirmUploadResponse.fromJson(Map<String, dynamic> json) =>
      ConfirmUploadResponse(
        objectKey: (json['object_key'] as String?)!,
        sizeBytes: (_int(json['size_bytes']))!,
        contentType: (json['content_type'] as String?)!,
        url: (json['url'] as String?)!,
      );
}

/// `ConsumedLineResponse` from the API schema.
class ConsumedLineResponse {
  final String itemName;
  final double grams;
  final double? cost;

  const ConsumedLineResponse({
    required this.itemName,
    required this.grams,
    this.cost,
  });

  factory ConsumedLineResponse.fromJson(Map<String, dynamic> json) =>
      ConsumedLineResponse(
        itemName: (json['item_name'] as String?)!,
        grams: (_double(json['grams']))!,
        cost: _double(json['cost']),
      );
}

/// `ConsumptionResponse` from the API schema.
class ConsumptionResponse {
  final List<ConsumedLineResponse> consumed;
  final List<String> unmatched;
  final double? totalCost;
  final double? costPerLoaf;
  final String? skippedReason;

  const ConsumptionResponse({
    required this.consumed,
    required this.unmatched,
    this.totalCost,
    this.costPerLoaf,
    this.skippedReason,
  });

  factory ConsumptionResponse.fromJson(Map<String, dynamic> json) =>
      ConsumptionResponse(
        consumed: (json['consumed'] == null
            ? null
            : (json['consumed'] as List)
                  .map(
                    (e) => (e == null
                        ? null
                        : ConsumedLineResponse.fromJson(
                            e as Map<String, dynamic>,
                          ))!,
                  )
                  .toList()
                  .cast<ConsumedLineResponse>())!,
        unmatched: (json['unmatched'] == null
            ? null
            : (json['unmatched'] as List)
                  .map((e) => (e as String?)!)
                  .toList()
                  .cast<String>())!,
        totalCost: _double(json['total_cost']),
        costPerLoaf: _double(json['cost_per_loaf']),
        skippedReason: json['skipped_reason'] as String?,
      );
}

/// `ConversionResult` from the API schema.
class ConversionResult {
  final double? value;
  final String unit;
  final String? basis;
  final bool? approximate;
  final String? sourceSlug;
  final String? error;

  const ConversionResult({
    this.value,
    required this.unit,
    this.basis,
    this.approximate,
    this.sourceSlug,
    this.error,
  });

  factory ConversionResult.fromJson(Map<String, dynamic> json) =>
      ConversionResult(
        value: _double(json['value']),
        unit: (json['unit'] as String?)!,
        basis: json['basis'] as String?,
        approximate: json['approximate'] as bool?,
        sourceSlug: json['source_slug'] as String?,
        error: json['error'] as String?,
      );
}

/// `ConvertItem` from the API schema.
class ConvertItem {
  final double value;
  final String from;
  final String to;
  final String? ingredient;
  final String? kind;

  const ConvertItem({
    required this.value,
    required this.from,
    required this.to,
    this.ingredient,
    this.kind,
  });

  factory ConvertItem.fromJson(Map<String, dynamic> json) => ConvertItem(
    value: (_double(json['value']))!,
    from: (json['from'] as String?)!,
    to: (json['to'] as String?)!,
    ingredient: json['ingredient'] as String?,
    kind: json['kind'] as String?,
  );
}

/// `ConvertRequest` from the API schema.
class ConvertRequest {
  final List<ConvertItem> items;

  const ConvertRequest({required this.items});

  factory ConvertRequest.fromJson(Map<String, dynamic> json) => ConvertRequest(
    items: (json['items'] == null
        ? null
        : (json['items'] as List)
              .map(
                (e) => (e == null
                    ? null
                    : ConvertItem.fromJson(e as Map<String, dynamic>))!,
              )
              .toList()
              .cast<ConvertItem>())!,
  );
}

/// `ConvertResponse` from the API schema.
class ConvertResponse {
  final List<ConversionResult> results;

  const ConvertResponse({required this.results});

  factory ConvertResponse.fromJson(Map<String, dynamic> json) =>
      ConvertResponse(
        results: (json['results'] == null
            ? null
            : (json['results'] as List)
                  .map(
                    (e) => (e == null
                        ? null
                        : ConversionResult.fromJson(
                            e as Map<String, dynamic>,
                          ))!,
                  )
                  .toList()
                  .cast<ConversionResult>())!,
      );
}

/// `CostReport` from the API schema.
class CostReport {
  final DateTime? fromDate;
  final DateTime? toDate;
  final double totalPurchasedCost;
  final double totalPurchasedG;
  final double totalConsumedCost;
  final double totalConsumedG;
  final double currentStockValue;
  final int bakesCosted;
  final double? averageCostPerBake;
  final double? averageCostPerLoaf;

  const CostReport({
    this.fromDate,
    this.toDate,
    required this.totalPurchasedCost,
    required this.totalPurchasedG,
    required this.totalConsumedCost,
    required this.totalConsumedG,
    required this.currentStockValue,
    required this.bakesCosted,
    this.averageCostPerBake,
    this.averageCostPerLoaf,
  });

  factory CostReport.fromJson(Map<String, dynamic> json) => CostReport(
    fromDate: _date(json['from_date']),
    toDate: _date(json['to_date']),
    totalPurchasedCost: (_double(json['total_purchased_cost']))!,
    totalPurchasedG: (_double(json['total_purchased_g']))!,
    totalConsumedCost: (_double(json['total_consumed_cost']))!,
    totalConsumedG: (_double(json['total_consumed_g']))!,
    currentStockValue: (_double(json['current_stock_value']))!,
    bakesCosted: (_int(json['bakes_costed']))!,
    averageCostPerBake: _double(json['average_cost_per_bake']),
    averageCostPerLoaf: _double(json['average_cost_per_loaf']),
  );
}

/// `CurrentUserResponse` from the API schema.
class CurrentUserResponse {
  final String id;
  final String email;
  final String role;
  final bool isVerified;
  final bool isSuspended;
  final DateTime createdAt;
  final DateTime? lastLoginAt;
  final OwnProfile profile;

  const CurrentUserResponse({
    required this.id,
    required this.email,
    required this.role,
    required this.isVerified,
    required this.isSuspended,
    required this.createdAt,
    this.lastLoginAt,
    required this.profile,
  });

  factory CurrentUserResponse.fromJson(Map<String, dynamic> json) =>
      CurrentUserResponse(
        id: (json['id'] as String?)!,
        email: (json['email'] as String?)!,
        role: (json['role'] as String?)!,
        isVerified: (json['is_verified'] as bool?)!,
        isSuspended: (json['is_suspended'] as bool?)!,
        createdAt: (_date(json['created_at']))!,
        lastLoginAt: _date(json['last_login_at']),
        profile: (json['profile'] == null
            ? null
            : OwnProfile.fromJson(json['profile'] as Map<String, dynamic>))!,
      );
}

/// Erasure is irreversible, so it takes both a password and a typed phrase.
class DeleteAccountRequest {
  final String password;
  final String confirm;

  const DeleteAccountRequest({required this.password, required this.confirm});

  factory DeleteAccountRequest.fromJson(Map<String, dynamic> json) =>
      DeleteAccountRequest(
        password: (json['password'] as String?)!,
        confirm: (json['confirm'] as String?)!,
      );
}

/// `DeleteAccountResponse` from the API schema.
class DeleteAccountResponse {
  final bool deleted;
  final Map<String, dynamic> rowsRemoved;
  final int photosRemoved;

  const DeleteAccountResponse({
    required this.deleted,
    required this.rowsRemoved,
    required this.photosRemoved,
  });

  factory DeleteAccountResponse.fromJson(Map<String, dynamic> json) =>
      DeleteAccountResponse(
        deleted: (json['deleted'] as bool?)!,
        rowsRemoved: (json['rows_removed'] == null
            ? null
            : Map<String, dynamic>.from(json['rows_removed'] as Map))!,
        photosRemoved: (_int(json['photos_removed']))!,
      );
}

/// `EmailChannelCreate` from the API schema.
class EmailChannelCreate {
  final String address;
  final String? label;

  const EmailChannelCreate({required this.address, this.label});

  factory EmailChannelCreate.fromJson(Map<String, dynamic> json) =>
      EmailChannelCreate(
        address: (json['address'] as String?)!,
        label: json['label'] as String?,
      );
}

/// Preview an ETA without starting anything.
class EstimateRequest {
  final String? stage;
  final double doughTempC;
  final double? starterPct;
  final double? targetRisePct;
  final double? vigour;

  const EstimateRequest({
    this.stage,
    required this.doughTempC,
    this.starterPct,
    this.targetRisePct,
    this.vigour,
  });

  factory EstimateRequest.fromJson(Map<String, dynamic> json) =>
      EstimateRequest(
        stage: json['stage'] as String?,
        doughTempC: (_double(json['dough_temp_c']))!,
        starterPct: _double(json['starter_pct']),
        targetRisePct: _double(json['target_rise_pct']),
        vigour: _double(json['vigour']),
      );
}

/// `EstimateResponse` from the API schema.
class EstimateResponse {
  final double hours;
  final double earliestHours;
  final double latestHours;
  final double risePerHourPct;

  const EstimateResponse({
    required this.hours,
    required this.earliestHours,
    required this.latestHours,
    required this.risePerHourPct,
  });

  factory EstimateResponse.fromJson(Map<String, dynamic> json) =>
      EstimateResponse(
        hours: (_double(json['hours']))!,
        earliestHours: (_double(json['earliest_hours']))!,
        latestHours: (_double(json['latest_hours']))!,
        risePerHourPct: (_double(json['rise_per_hour_pct']))!,
      );
}

/// `EventCatalogueItem` from the API schema.
class EventCatalogueItem {
  final String event;
  final String title;
  final String urgency;
  final String icon;
  final List<String> defaultChannels;
  final bool ignoresQuietHours;

  const EventCatalogueItem({
    required this.event,
    required this.title,
    required this.urgency,
    required this.icon,
    required this.defaultChannels,
    required this.ignoresQuietHours,
  });

  factory EventCatalogueItem.fromJson(Map<String, dynamic> json) =>
      EventCatalogueItem(
        event: (json['event'] as String?)!,
        title: (json['title'] as String?)!,
        urgency: (json['urgency'] as String?)!,
        icon: (json['icon'] as String?)!,
        defaultChannels: (json['default_channels'] == null
            ? null
            : (json['default_channels'] as List)
                  .map((e) => (e as String?)!)
                  .toList()
                  .cast<String>())!,
        ignoresQuietHours: (json['ignores_quiet_hours'] as bool?)!,
      );
}

/// `FeedingCreate` from the API schema.
class FeedingCreate {
  final DateTime? fedAt;
  final double starterG;
  final double flourG;
  final double waterG;
  final Map<String, dynamic>? flourBlend;
  final double? ambientTempC;
  final String? notes;

  const FeedingCreate({
    this.fedAt,
    required this.starterG,
    required this.flourG,
    required this.waterG,
    this.flourBlend,
    this.ambientTempC,
    this.notes,
  });

  factory FeedingCreate.fromJson(Map<String, dynamic> json) => FeedingCreate(
    fedAt: _date(json['fed_at']),
    starterG: (_double(json['starter_g']))!,
    flourG: (_double(json['flour_g']))!,
    waterG: (_double(json['water_g']))!,
    flourBlend: json['flour_blend'] == null
        ? null
        : Map<String, dynamic>.from(json['flour_blend'] as Map),
    ambientTempC: _double(json['ambient_temp_c']),
    notes: json['notes'] as String?,
  );
}

/// `FeedingResponse` from the API schema.
class FeedingResponse {
  final String id;
  final String starterId;
  final DateTime fedAt;
  final double starterG;
  final double flourG;
  final double waterG;
  final double hydrationPct;
  final Map<String, dynamic>? flourBlend;
  final double? ambientTempC;
  final String? notes;

  const FeedingResponse({
    required this.id,
    required this.starterId,
    required this.fedAt,
    required this.starterG,
    required this.flourG,
    required this.waterG,
    required this.hydrationPct,
    this.flourBlend,
    this.ambientTempC,
    this.notes,
  });

  factory FeedingResponse.fromJson(Map<String, dynamic> json) =>
      FeedingResponse(
        id: (json['id'] as String?)!,
        starterId: (json['starter_id'] as String?)!,
        fedAt: (_date(json['fed_at']))!,
        starterG: (_double(json['starter_g']))!,
        flourG: (_double(json['flour_g']))!,
        waterG: (_double(json['water_g']))!,
        hydrationPct: (_double(json['hydration_pct']))!,
        flourBlend: json['flour_blend'] == null
            ? null
            : Map<String, dynamic>.from(json['flour_blend'] as Map),
        ambientTempC: _double(json['ambient_temp_c']),
        notes: json['notes'] as String?,
      );
}

/// `ForgotPasswordRequest` from the API schema.
class ForgotPasswordRequest {
  final String email;

  const ForgotPasswordRequest({required this.email});

  factory ForgotPasswordRequest.fromJson(Map<String, dynamic> json) =>
      ForgotPasswordRequest(email: (json['email'] as String?)!);
}

/// `HealthResponse` from the API schema.
class HealthResponse {
  final String status;
  final String version;
  final Map<String, dynamic> checks;

  const HealthResponse({
    required this.status,
    required this.version,
    required this.checks,
  });

  factory HealthResponse.fromJson(Map<String, dynamic> json) => HealthResponse(
    status: (json['status'] as String?)!,
    version: (json['version'] as String?)!,
    checks: (json['checks'] == null
        ? null
        : Map<String, dynamic>.from(json['checks'] as Map))!,
  );
}

/// `InboxItem` from the API schema.
class InboxItem {
  final String id;
  final String event;
  final String title;
  final String body;
  final Map<String, dynamic> data;
  final DateTime? readAt;
  final DateTime createdAt;

  const InboxItem({
    required this.id,
    required this.event,
    required this.title,
    required this.body,
    required this.data,
    this.readAt,
    required this.createdAt,
  });

  factory InboxItem.fromJson(Map<String, dynamic> json) => InboxItem(
    id: (json['id'] as String?)!,
    event: (json['event'] as String?)!,
    title: (json['title'] as String?)!,
    body: (json['body'] as String?)!,
    data: (json['data'] == null
        ? null
        : Map<String, dynamic>.from(json['data'] as Map))!,
    readAt: _date(json['read_at']),
    createdAt: (_date(json['created_at']))!,
  );
}

/// `InboxPage` from the API schema.
class InboxPage {
  final List<InboxItem> items;
  final int unreadCount;

  const InboxPage({required this.items, required this.unreadCount});

  factory InboxPage.fromJson(Map<String, dynamic> json) => InboxPage(
    items: (json['items'] == null
        ? null
        : (json['items'] as List)
              .map(
                (e) => (e == null
                    ? null
                    : InboxItem.fromJson(e as Map<String, dynamic>))!,
              )
              .toList()
              .cast<InboxItem>())!,
    unreadCount: (_int(json['unread_count']))!,
  );
}

/// One recipe line, as a percentage *or* as an amount.
class IngredientInput {
  final String name;
  final String kind;
  final double? percentage;
  final double? amount;
  final String? unit;

  const IngredientInput({
    required this.name,
    required this.kind,
    this.percentage,
    this.amount,
    this.unit,
  });

  factory IngredientInput.fromJson(Map<String, dynamic> json) =>
      IngredientInput(
        name: (json['name'] as String?)!,
        kind: (json['kind'] as String?)!,
        percentage: _double(json['percentage']),
        amount: _double(json['amount']),
        unit: json['unit'] as String?,
      );
}

/// `IngredientMeasureResponse` from the API schema.
class IngredientMeasureResponse {
  final String slug;
  final String name;
  final String kind;
  final double gramsPerCup;
  final String method;
  final String source;
  final List<String> aliases;
  final bool volumeAllowed;
  final String? reason;
  final bool? overridden;

  const IngredientMeasureResponse({
    required this.slug,
    required this.name,
    required this.kind,
    required this.gramsPerCup,
    required this.method,
    required this.source,
    required this.aliases,
    required this.volumeAllowed,
    this.reason,
    this.overridden,
  });

  factory IngredientMeasureResponse.fromJson(Map<String, dynamic> json) =>
      IngredientMeasureResponse(
        slug: (json['slug'] as String?)!,
        name: (json['name'] as String?)!,
        kind: (json['kind'] as String?)!,
        gramsPerCup: (_double(json['grams_per_cup']))!,
        method: (json['method'] as String?)!,
        source: (json['source'] as String?)!,
        aliases: (json['aliases'] == null
            ? null
            : (json['aliases'] as List)
                  .map((e) => (e as String?)!)
                  .toList()
                  .cast<String>())!,
        volumeAllowed: (json['volume_allowed'] as bool?)!,
        reason: json['reason'] as String?,
        overridden: json['overridden'] as bool?,
      );
}

/// `IngredientResponse` from the API schema.
class IngredientResponse {
  final String name;
  final String kind;
  final double percentage;
  final int sortOrder;

  const IngredientResponse({
    required this.name,
    required this.kind,
    required this.percentage,
    required this.sortOrder,
  });

  factory IngredientResponse.fromJson(Map<String, dynamic> json) =>
      IngredientResponse(
        name: (json['name'] as String?)!,
        kind: (json['kind'] as String?)!,
        percentage: (_double(json['percentage']))!,
        sortOrder: (_int(json['sort_order']))!,
      );
}

/// `InstanceStats` from the API schema.
class InstanceStats {
  final int usersTotal;
  final int usersVerified;
  final int usersSuspended;
  final int starters;
  final int feedings;
  final int proofSessions;
  final int bakes;
  final int recipes;
  final int recipesPublic;
  final int photos;
  final int notificationsPending;
  final int notificationsFailed;
  final int xpAwarded;
  final int achievementsEarned;
  final int databaseBytes;

  const InstanceStats({
    required this.usersTotal,
    required this.usersVerified,
    required this.usersSuspended,
    required this.starters,
    required this.feedings,
    required this.proofSessions,
    required this.bakes,
    required this.recipes,
    required this.recipesPublic,
    required this.photos,
    required this.notificationsPending,
    required this.notificationsFailed,
    required this.xpAwarded,
    required this.achievementsEarned,
    required this.databaseBytes,
  });

  factory InstanceStats.fromJson(Map<String, dynamic> json) => InstanceStats(
    usersTotal: (_int(json['users_total']))!,
    usersVerified: (_int(json['users_verified']))!,
    usersSuspended: (_int(json['users_suspended']))!,
    starters: (_int(json['starters']))!,
    feedings: (_int(json['feedings']))!,
    proofSessions: (_int(json['proof_sessions']))!,
    bakes: (_int(json['bakes']))!,
    recipes: (_int(json['recipes']))!,
    recipesPublic: (_int(json['recipes_public']))!,
    photos: (_int(json['photos']))!,
    notificationsPending: (_int(json['notifications_pending']))!,
    notificationsFailed: (_int(json['notifications_failed']))!,
    xpAwarded: (_int(json['xp_awarded']))!,
    achievementsEarned: (_int(json['achievements_earned']))!,
    databaseBytes: (_int(json['database_bytes']))!,
  );
}

/// `ItemCreate` from the API schema.
class ItemCreate {
  final String name;
  final String? kind;
  final double? lowThresholdG;
  final String? notes;

  const ItemCreate({
    required this.name,
    this.kind,
    this.lowThresholdG,
    this.notes,
  });

  factory ItemCreate.fromJson(Map<String, dynamic> json) => ItemCreate(
    name: (json['name'] as String?)!,
    kind: json['kind'] as String?,
    lowThresholdG: _double(json['low_threshold_g']),
    notes: json['notes'] as String?,
  );
}

/// `ItemResponse` from the API schema.
class ItemResponse {
  final String id;
  final String name;
  final String kind;
  final double lowThresholdG;
  final String? notes;
  final DateTime createdAt;
  final double onHandG;
  final MeasureDisplay? onHandDisplay;
  final double? averageCostPerKg;
  final double? stockValue;
  final bool isLow;

  const ItemResponse({
    required this.id,
    required this.name,
    required this.kind,
    required this.lowThresholdG,
    this.notes,
    required this.createdAt,
    required this.onHandG,
    this.onHandDisplay,
    this.averageCostPerKg,
    this.stockValue,
    required this.isLow,
  });

  factory ItemResponse.fromJson(Map<String, dynamic> json) => ItemResponse(
    id: (json['id'] as String?)!,
    name: (json['name'] as String?)!,
    kind: (json['kind'] as String?)!,
    lowThresholdG: (_double(json['low_threshold_g']))!,
    notes: json['notes'] as String?,
    createdAt: (_date(json['created_at']))!,
    onHandG: (_double(json['on_hand_g']))!,
    onHandDisplay: json['on_hand_display'] == null
        ? null
        : MeasureDisplay.fromJson(
            json['on_hand_display'] as Map<String, dynamic>,
          ),
    averageCostPerKg: _double(json['average_cost_per_kg']),
    stockValue: _double(json['stock_value']),
    isLow: (json['is_low'] as bool?)!,
  );
}

/// `ItemUpdate` from the API schema.
class ItemUpdate {
  final String? name;
  final String? kind;
  final double? lowThresholdG;
  final String? notes;

  const ItemUpdate({this.name, this.kind, this.lowThresholdG, this.notes});

  factory ItemUpdate.fromJson(Map<String, dynamic> json) => ItemUpdate(
    name: json['name'] as String?,
    kind: json['kind'] as String?,
    lowThresholdG: _double(json['low_threshold_g']),
    notes: json['notes'] as String?,
  );
}

/// `LeaderboardPage` from the API schema.
class LeaderboardPage {
  final String seasonId;
  final String seasonName;
  final String category;
  final List<LeaderboardRow> rows;
  final DateTime? refreshedAt;

  const LeaderboardPage({
    required this.seasonId,
    required this.seasonName,
    required this.category,
    required this.rows,
    this.refreshedAt,
  });

  factory LeaderboardPage.fromJson(Map<String, dynamic> json) =>
      LeaderboardPage(
        seasonId: (json['season_id'] as String?)!,
        seasonName: (json['season_name'] as String?)!,
        category: (json['category'] as String?)!,
        rows: (json['rows'] == null
            ? null
            : (json['rows'] as List)
                  .map(
                    (e) => (e == null
                        ? null
                        : LeaderboardRow.fromJson(e as Map<String, dynamic>))!,
                  )
                  .toList()
                  .cast<LeaderboardRow>())!,
        refreshedAt: _date(json['refreshed_at']),
      );
}

/// `LeaderboardRow` from the API schema.
class LeaderboardRow {
  final int rank;
  final String? handle;
  final String? displayName;
  final bool isYou;
  final int seasonXp;
  final int lifetimeXp;
  final int bakeCount;
  final int longestStreak;
  final double? averageCrumb;
  final int achievementCount;
  final String tier;

  const LeaderboardRow({
    required this.rank,
    this.handle,
    this.displayName,
    required this.isYou,
    required this.seasonXp,
    required this.lifetimeXp,
    required this.bakeCount,
    required this.longestStreak,
    this.averageCrumb,
    required this.achievementCount,
    required this.tier,
  });

  factory LeaderboardRow.fromJson(Map<String, dynamic> json) => LeaderboardRow(
    rank: (_int(json['rank']))!,
    handle: json['handle'] as String?,
    displayName: json['display_name'] as String?,
    isYou: (json['is_you'] as bool?)!,
    seasonXp: (_int(json['season_xp']))!,
    lifetimeXp: (_int(json['lifetime_xp']))!,
    bakeCount: (_int(json['bake_count']))!,
    longestStreak: (_int(json['longest_streak']))!,
    averageCrumb: _double(json['average_crumb']),
    achievementCount: (_int(json['achievement_count']))!,
    tier: (json['tier'] as String?)!,
  );
}

/// `LoginRequest` from the API schema.
class LoginRequest {
  final String email;
  final String password;

  const LoginRequest({required this.email, required this.password});

  factory LoginRequest.fromJson(Map<String, dynamic> json) => LoginRequest(
    email: (json['email'] as String?)!,
    password: (json['password'] as String?)!,
  );
}

/// `MarkReadRequest` from the API schema.
class MarkReadRequest {
  final List<String>? ids;
  final bool? all;

  const MarkReadRequest({this.ids, this.all});

  factory MarkReadRequest.fromJson(Map<String, dynamic> json) =>
      MarkReadRequest(
        ids: json['ids'] == null
            ? null
            : (json['ids'] as List)
                  .map((e) => (e as String?)!)
                  .toList()
                  .cast<String>(),
        all: json['all'] as bool?,
      );
}

/// A quantity rendered for a baker, carrying its own inaccuracy.
class MeasureDisplay {
  final String text;
  final String system;
  final String basis;
  final bool approximate;
  final double grams;
  final double driftPct;
  final bool adviseWeighing;

  const MeasureDisplay({
    required this.text,
    required this.system,
    required this.basis,
    required this.approximate,
    required this.grams,
    required this.driftPct,
    required this.adviseWeighing,
  });

  factory MeasureDisplay.fromJson(Map<String, dynamic> json) => MeasureDisplay(
    text: (json['text'] as String?)!,
    system: (json['system'] as String?)!,
    basis: (json['basis'] as String?)!,
    approximate: (json['approximate'] as bool?)!,
    grams: (_double(json['grams']))!,
    driftPct: (_double(json['drift_pct']))!,
    adviseWeighing: (json['advise_weighing'] as bool?)!,
  );
}

/// `MessageResponse` from the API schema.
class MessageResponse {
  final String message;

  const MessageResponse({required this.message});

  factory MessageResponse.fromJson(Map<String, dynamic> json) =>
      MessageResponse(message: (json['message'] as String?)!);
}

/// A published recipe awaiting a look.
class ModerationItem {
  final String recipeId;
  final String name;
  final String? description;
  final String ownerId;
  final String ownerHandle;
  final bool ownerSuspended;
  final List<String> tags;
  final int starCount;
  final int forkCount;
  final DateTime createdAt;

  const ModerationItem({
    required this.recipeId,
    required this.name,
    this.description,
    required this.ownerId,
    required this.ownerHandle,
    required this.ownerSuspended,
    required this.tags,
    required this.starCount,
    required this.forkCount,
    required this.createdAt,
  });

  factory ModerationItem.fromJson(Map<String, dynamic> json) => ModerationItem(
    recipeId: (json['recipe_id'] as String?)!,
    name: (json['name'] as String?)!,
    description: json['description'] as String?,
    ownerId: (json['owner_id'] as String?)!,
    ownerHandle: (json['owner_handle'] as String?)!,
    ownerSuspended: (json['owner_suspended'] as bool?)!,
    tags: (json['tags'] == null
        ? null
        : (json['tags'] as List)
              .map((e) => (e as String?)!)
              .toList()
              .cast<String>())!,
    starCount: (_int(json['star_count']))!,
    forkCount: (_int(json['fork_count']))!,
    createdAt: (_date(json['created_at']))!,
  );
}

/// `MyRankResponse` from the API schema.
class MyRankResponse {
  final String seasonName;
  final int? rank;
  final int totalRanked;
  final List<LeaderboardRow> neighbours;

  const MyRankResponse({
    required this.seasonName,
    this.rank,
    required this.totalRanked,
    required this.neighbours,
  });

  factory MyRankResponse.fromJson(Map<String, dynamic> json) => MyRankResponse(
    seasonName: (json['season_name'] as String?)!,
    rank: _int(json['rank']),
    totalRanked: (_int(json['total_ranked']))!,
    neighbours: (json['neighbours'] == null
        ? null
        : (json['neighbours'] as List)
              .map(
                (e) => (e == null
                    ? null
                    : LeaderboardRow.fromJson(e as Map<String, dynamic>))!,
              )
              .toList()
              .cast<LeaderboardRow>())!,
  );
}

/// `NtfyChannelCreate` from the API schema.
class NtfyChannelCreate {
  final String topic;
  final String? token;
  final String? label;

  const NtfyChannelCreate({required this.topic, this.token, this.label});

  factory NtfyChannelCreate.fromJson(Map<String, dynamic> json) =>
      NtfyChannelCreate(
        topic: (json['topic'] as String?)!,
        token: json['token'] as String?,
        label: json['label'] as String?,
      );
}

/// `ObservationCreate` from the API schema.
class ObservationCreate {
  final DateTime? observedAt;
  final String? feedingId;
  final double? riseMultiple;
  final bool? peaked;
  final bool? floatTestPassed;
  final String? aroma;
  final double? doughTempC;
  final String? notes;

  const ObservationCreate({
    this.observedAt,
    this.feedingId,
    this.riseMultiple,
    this.peaked,
    this.floatTestPassed,
    this.aroma,
    this.doughTempC,
    this.notes,
  });

  factory ObservationCreate.fromJson(Map<String, dynamic> json) =>
      ObservationCreate(
        observedAt: _date(json['observed_at']),
        feedingId: json['feeding_id'] as String?,
        riseMultiple: _double(json['rise_multiple']),
        peaked: json['peaked'] as bool?,
        floatTestPassed: json['float_test_passed'] as bool?,
        aroma: json['aroma'] as String?,
        doughTempC: _double(json['dough_temp_c']),
        notes: json['notes'] as String?,
      );
}

/// `ObservationResponse` from the API schema.
class ObservationResponse {
  final String id;
  final String starterId;
  final String? feedingId;
  final DateTime observedAt;
  final double? riseMultiple;
  final bool peaked;
  final bool? floatTestPassed;
  final String? aroma;
  final double? doughTempC;
  final String? photoObjectKey;
  final String? notes;

  const ObservationResponse({
    required this.id,
    required this.starterId,
    this.feedingId,
    required this.observedAt,
    this.riseMultiple,
    required this.peaked,
    this.floatTestPassed,
    this.aroma,
    this.doughTempC,
    this.photoObjectKey,
    this.notes,
  });

  factory ObservationResponse.fromJson(Map<String, dynamic> json) =>
      ObservationResponse(
        id: (json['id'] as String?)!,
        starterId: (json['starter_id'] as String?)!,
        feedingId: json['feeding_id'] as String?,
        observedAt: (_date(json['observed_at']))!,
        riseMultiple: _double(json['rise_multiple']),
        peaked: (json['peaked'] as bool?)!,
        floatTestPassed: json['float_test_passed'] as bool?,
        aroma: json['aroma'] as String?,
        doughTempC: _double(json['dough_temp_c']),
        photoObjectKey: json['photo_object_key'] as String?,
        notes: json['notes'] as String?,
      );
}

/// `OverrideRequest` from the API schema.
class OverrideRequest {
  final double gramsPerCup;
  final String? note;

  const OverrideRequest({required this.gramsPerCup, this.note});

  factory OverrideRequest.fromJson(Map<String, dynamic> json) =>
      OverrideRequest(
        gramsPerCup: (_double(json['grams_per_cup']))!,
        note: json['note'] as String?,
      );
}

/// `OwnProfile` from the API schema.
class OwnProfile {
  final String handle;
  final String displayName;
  final String? bio;
  final String? avatarObjectKey;
  final bool isPublic;
  final String timezone;
  final String units;

  const OwnProfile({
    required this.handle,
    required this.displayName,
    this.bio,
    this.avatarObjectKey,
    required this.isPublic,
    required this.timezone,
    required this.units,
  });

  factory OwnProfile.fromJson(Map<String, dynamic> json) => OwnProfile(
    handle: (json['handle'] as String?)!,
    displayName: (json['display_name'] as String?)!,
    bio: json['bio'] as String?,
    avatarObjectKey: json['avatar_object_key'] as String?,
    isPublic: (json['is_public'] as bool?)!,
    timezone: (json['timezone'] as String?)!,
    units: (json['units'] as String?)!,
  );
}

/// `PhotoAttach` from the API schema.
class PhotoAttach {
  final String objectKey;
  final String? kind;
  final String? caption;
  final int? sortOrder;

  const PhotoAttach({
    required this.objectKey,
    this.kind,
    this.caption,
    this.sortOrder,
  });

  factory PhotoAttach.fromJson(Map<String, dynamic> json) => PhotoAttach(
    objectKey: (json['object_key'] as String?)!,
    kind: json['kind'] as String?,
    caption: json['caption'] as String?,
    sortOrder: _int(json['sort_order']),
  );
}

/// `PhotoResponse` from the API schema.
class PhotoResponse {
  final String id;
  final String objectKey;
  final String kind;
  final String? caption;
  final int sortOrder;
  final int? sizeBytes;
  final String url;

  const PhotoResponse({
    required this.id,
    required this.objectKey,
    required this.kind,
    this.caption,
    required this.sortOrder,
    this.sizeBytes,
    required this.url,
  });

  factory PhotoResponse.fromJson(Map<String, dynamic> json) => PhotoResponse(
    id: (json['id'] as String?)!,
    objectKey: (json['object_key'] as String?)!,
    kind: (json['kind'] as String?)!,
    caption: json['caption'] as String?,
    sortOrder: (_int(json['sort_order']))!,
    sizeBytes: _int(json['size_bytes']),
    url: (json['url'] as String?)!,
  );
}

/// `PresignUploadRequest` from the API schema.
class PresignUploadRequest {
  final String contentType;
  final String? purpose;

  const PresignUploadRequest({required this.contentType, this.purpose});

  factory PresignUploadRequest.fromJson(Map<String, dynamic> json) =>
      PresignUploadRequest(
        contentType: (json['content_type'] as String?)!,
        purpose: json['purpose'] as String?,
      );
}

/// A one-shot grant to POST a file straight to object storage.
class PresignUploadResponse {
  final String objectKey;
  final String url;
  final Map<String, dynamic> fields;
  final int maxBytes;
  final int expiresIn;

  const PresignUploadResponse({
    required this.objectKey,
    required this.url,
    required this.fields,
    required this.maxBytes,
    required this.expiresIn,
  });

  factory PresignUploadResponse.fromJson(Map<String, dynamic> json) =>
      PresignUploadResponse(
        objectKey: (json['object_key'] as String?)!,
        url: (json['url'] as String?)!,
        fields: (json['fields'] == null
            ? null
            : Map<String, dynamic>.from(json['fields'] as Map))!,
        maxBytes: (_int(json['max_bytes']))!,
        expiresIn: (_int(json['expires_in']))!,
      );
}

/// All fields optional — only what is supplied is changed.
class ProfileUpdate {
  final String? displayName;
  final String? bio;
  final bool? isPublic;
  final String? timezone;
  final String? units;

  const ProfileUpdate({
    this.displayName,
    this.bio,
    this.isPublic,
    this.timezone,
    this.units,
  });

  factory ProfileUpdate.fromJson(Map<String, dynamic> json) => ProfileUpdate(
    displayName: json['display_name'] as String?,
    bio: json['bio'] as String?,
    isPublic: json['is_public'] as bool?,
    timezone: json['timezone'] as String?,
    units: json['units'] as String?,
  );
}

/// `ProofCheckCreate` from the API schema.
class ProofCheckCreate {
  final DateTime? checkedAt;
  final double risePct;
  final double? doughTempC;
  final double? doughTempF;
  final String? pokeTest;
  final String? notes;

  const ProofCheckCreate({
    this.checkedAt,
    required this.risePct,
    this.doughTempC,
    this.doughTempF,
    this.pokeTest,
    this.notes,
  });

  factory ProofCheckCreate.fromJson(Map<String, dynamic> json) =>
      ProofCheckCreate(
        checkedAt: _date(json['checked_at']),
        risePct: (_double(json['rise_pct']))!,
        doughTempC: _double(json['dough_temp_c']),
        doughTempF: _double(json['dough_temp_f']),
        pokeTest: json['poke_test'] as String?,
        notes: json['notes'] as String?,
      );
}

/// `ProofCheckResponse` from the API schema.
class ProofCheckResponse {
  final String id;
  final String sessionId;
  final DateTime checkedAt;
  final double risePct;
  final double? doughTempC;
  final String? pokeTest;
  final String? photoObjectKey;
  final String? notes;

  const ProofCheckResponse({
    required this.id,
    required this.sessionId,
    required this.checkedAt,
    required this.risePct,
    this.doughTempC,
    this.pokeTest,
    this.photoObjectKey,
    this.notes,
  });

  factory ProofCheckResponse.fromJson(Map<String, dynamic> json) =>
      ProofCheckResponse(
        id: (json['id'] as String?)!,
        sessionId: (json['session_id'] as String?)!,
        checkedAt: (_date(json['checked_at']))!,
        risePct: (_double(json['rise_pct']))!,
        doughTempC: _double(json['dough_temp_c']),
        pokeTest: json['poke_test'] as String?,
        photoObjectKey: json['photo_object_key'] as String?,
        notes: json['notes'] as String?,
      );
}

/// `ProofCompleteRequest` from the API schema.
class ProofCompleteRequest {
  final DateTime? actualEndAt;
  final double? finalRisePct;
  final String? notes;

  const ProofCompleteRequest({this.actualEndAt, this.finalRisePct, this.notes});

  factory ProofCompleteRequest.fromJson(Map<String, dynamic> json) =>
      ProofCompleteRequest(
        actualEndAt: _date(json['actual_end_at']),
        finalRisePct: _double(json['final_rise_pct']),
        notes: json['notes'] as String?,
      );
}

/// `ProofSessionCreate` from the API schema.
class ProofSessionCreate {
  final String stage;
  final String? starterId;
  final String? bakeId;
  final DateTime? startedAt;
  final double? doughTempC;
  final double? doughTempF;
  final double? ambientTempC;
  final double? ambientTempF;
  final double? starterPct;
  final double? hydrationPct;
  final double? targetRisePct;
  final int? plannedDurationMinutes;
  final String? notes;

  const ProofSessionCreate({
    required this.stage,
    this.starterId,
    this.bakeId,
    this.startedAt,
    this.doughTempC,
    this.doughTempF,
    this.ambientTempC,
    this.ambientTempF,
    this.starterPct,
    this.hydrationPct,
    this.targetRisePct,
    this.plannedDurationMinutes,
    this.notes,
  });

  factory ProofSessionCreate.fromJson(Map<String, dynamic> json) =>
      ProofSessionCreate(
        stage: (json['stage'] as String?)!,
        starterId: json['starter_id'] as String?,
        bakeId: json['bake_id'] as String?,
        startedAt: _date(json['started_at']),
        doughTempC: _double(json['dough_temp_c']),
        doughTempF: _double(json['dough_temp_f']),
        ambientTempC: _double(json['ambient_temp_c']),
        ambientTempF: _double(json['ambient_temp_f']),
        starterPct: _double(json['starter_pct']),
        hydrationPct: _double(json['hydration_pct']),
        targetRisePct: _double(json['target_rise_pct']),
        plannedDurationMinutes: _int(json['planned_duration_minutes']),
        notes: json['notes'] as String?,
      );
}

/// `ProofSessionResponse` from the API schema.
class ProofSessionResponse {
  final String id;
  final String? starterId;
  final String? bakeId;
  final String stage;
  final String status;
  final DateTime startedAt;
  final DateTime? actualEndAt;
  final double doughTempC;
  final double? ambientTempC;
  final double starterPct;
  final double? hydrationPct;
  final double targetRisePct;
  final int? plannedDurationMinutes;
  final DateTime predictedEndAt;
  final DateTime windowStartAt;
  final DateTime windowEndAt;
  final double vigourUsed;
  final String? notes;

  const ProofSessionResponse({
    required this.id,
    this.starterId,
    this.bakeId,
    required this.stage,
    required this.status,
    required this.startedAt,
    this.actualEndAt,
    required this.doughTempC,
    this.ambientTempC,
    required this.starterPct,
    this.hydrationPct,
    required this.targetRisePct,
    this.plannedDurationMinutes,
    required this.predictedEndAt,
    required this.windowStartAt,
    required this.windowEndAt,
    required this.vigourUsed,
    this.notes,
  });

  factory ProofSessionResponse.fromJson(Map<String, dynamic> json) =>
      ProofSessionResponse(
        id: (json['id'] as String?)!,
        starterId: json['starter_id'] as String?,
        bakeId: json['bake_id'] as String?,
        stage: (json['stage'] as String?)!,
        status: (json['status'] as String?)!,
        startedAt: (_date(json['started_at']))!,
        actualEndAt: _date(json['actual_end_at']),
        doughTempC: (_double(json['dough_temp_c']))!,
        ambientTempC: _double(json['ambient_temp_c']),
        starterPct: (_double(json['starter_pct']))!,
        hydrationPct: _double(json['hydration_pct']),
        targetRisePct: (_double(json['target_rise_pct']))!,
        plannedDurationMinutes: _int(json['planned_duration_minutes']),
        predictedEndAt: (_date(json['predicted_end_at']))!,
        windowStartAt: (_date(json['window_start_at']))!,
        windowEndAt: (_date(json['window_end_at']))!,
        vigourUsed: (_double(json['vigour_used']))!,
        notes: json['notes'] as String?,
      );
}

/// What anyone may see. Never includes the email address.
class PublicProfile {
  final String handle;
  final String displayName;
  final String? bio;
  final String? avatarObjectKey;
  final DateTime createdAt;

  const PublicProfile({
    required this.handle,
    required this.displayName,
    this.bio,
    this.avatarObjectKey,
    required this.createdAt,
  });

  factory PublicProfile.fromJson(Map<String, dynamic> json) => PublicProfile(
    handle: (json['handle'] as String?)!,
    displayName: (json['display_name'] as String?)!,
    bio: json['bio'] as String?,
    avatarObjectKey: json['avatar_object_key'] as String?,
    createdAt: (_date(json['created_at']))!,
  );
}

/// Listing shape for the public browse view — no step-by-step method.
class PublicRecipeSummary {
  final String id;
  final String name;
  final String? description;
  final String ownerHandle;
  final List<String> tags;
  final int starCount;
  final int forkCount;
  final DateTime createdAt;

  const PublicRecipeSummary({
    required this.id,
    required this.name,
    this.description,
    required this.ownerHandle,
    required this.tags,
    required this.starCount,
    required this.forkCount,
    required this.createdAt,
  });

  factory PublicRecipeSummary.fromJson(Map<String, dynamic> json) =>
      PublicRecipeSummary(
        id: (json['id'] as String?)!,
        name: (json['name'] as String?)!,
        description: json['description'] as String?,
        ownerHandle: (json['owner_handle'] as String?)!,
        tags: (json['tags'] == null
            ? null
            : (json['tags'] as List)
                  .map((e) => (e as String?)!)
                  .toList()
                  .cast<String>())!,
        starCount: (_int(json['star_count']))!,
        forkCount: (_int(json['fork_count']))!,
        createdAt: (_date(json['created_at']))!,
      );
}

/// `RatingInput` from the API schema.
class RatingInput {
  final int overall;
  final int? crumb;
  final int? ovenSpring;
  final int? crust;
  final int? sourness;
  final String? notes;

  const RatingInput({
    required this.overall,
    this.crumb,
    this.ovenSpring,
    this.crust,
    this.sourness,
    this.notes,
  });

  factory RatingInput.fromJson(Map<String, dynamic> json) => RatingInput(
    overall: (_int(json['overall']))!,
    crumb: _int(json['crumb']),
    ovenSpring: _int(json['oven_spring']),
    crust: _int(json['crust']),
    sourness: _int(json['sourness']),
    notes: json['notes'] as String?,
  );
}

/// `RatingResponse` from the API schema.
class RatingResponse {
  final int overall;
  final int? crumb;
  final int? ovenSpring;
  final int? crust;
  final int? sourness;
  final String? notes;

  const RatingResponse({
    required this.overall,
    this.crumb,
    this.ovenSpring,
    this.crust,
    this.sourness,
    this.notes,
  });

  factory RatingResponse.fromJson(Map<String, dynamic> json) => RatingResponse(
    overall: (_int(json['overall']))!,
    crumb: _int(json['crumb']),
    ovenSpring: _int(json['oven_spring']),
    crust: _int(json['crust']),
    sourness: _int(json['sourness']),
    notes: json['notes'] as String?,
  );
}

/// `RecipeCreate` from the API schema.
class RecipeCreate {
  final String name;
  final String? description;
  final bool? isPublic;
  final double? defaultDoughWeightG;
  final double? starterHydrationPct;
  final List<String>? tags;
  final List<Map<String, dynamic>>? steps;
  final List<IngredientInput> ingredients;

  const RecipeCreate({
    required this.name,
    this.description,
    this.isPublic,
    this.defaultDoughWeightG,
    this.starterHydrationPct,
    this.tags,
    this.steps,
    required this.ingredients,
  });

  factory RecipeCreate.fromJson(Map<String, dynamic> json) => RecipeCreate(
    name: (json['name'] as String?)!,
    description: json['description'] as String?,
    isPublic: json['is_public'] as bool?,
    defaultDoughWeightG: _double(json['default_dough_weight_g']),
    starterHydrationPct: _double(json['starter_hydration_pct']),
    tags: json['tags'] == null
        ? null
        : (json['tags'] as List)
              .map((e) => (e as String?)!)
              .toList()
              .cast<String>(),
    steps: json['steps'] == null
        ? null
        : (json['steps'] as List)
              .map(
                (e) =>
                    (e == null ? null : Map<String, dynamic>.from(e as Map))!,
              )
              .toList()
              .cast<Map<String, dynamic>>(),
    ingredients: (json['ingredients'] == null
        ? null
        : (json['ingredients'] as List)
              .map(
                (e) => (e == null
                    ? null
                    : IngredientInput.fromJson(e as Map<String, dynamic>))!,
              )
              .toList()
              .cast<IngredientInput>())!,
  );
}

/// `RecipeResponse` from the API schema.
class RecipeResponse {
  final String id;
  final String ownerId;
  final String name;
  final String? description;
  final bool isPublic;
  final String? forkedFromId;
  final int version;
  final double defaultDoughWeightG;
  final double starterHydrationPct;
  final List<String> tags;
  final List<Map<String, dynamic>> steps;
  final int starCount;
  final int forkCount;
  final DateTime createdAt;
  final List<IngredientResponse> ingredients;

  const RecipeResponse({
    required this.id,
    required this.ownerId,
    required this.name,
    this.description,
    required this.isPublic,
    this.forkedFromId,
    required this.version,
    required this.defaultDoughWeightG,
    required this.starterHydrationPct,
    required this.tags,
    required this.steps,
    required this.starCount,
    required this.forkCount,
    required this.createdAt,
    required this.ingredients,
  });

  factory RecipeResponse.fromJson(Map<String, dynamic> json) => RecipeResponse(
    id: (json['id'] as String?)!,
    ownerId: (json['owner_id'] as String?)!,
    name: (json['name'] as String?)!,
    description: json['description'] as String?,
    isPublic: (json['is_public'] as bool?)!,
    forkedFromId: json['forked_from_id'] as String?,
    version: (_int(json['version']))!,
    defaultDoughWeightG: (_double(json['default_dough_weight_g']))!,
    starterHydrationPct: (_double(json['starter_hydration_pct']))!,
    tags: (json['tags'] == null
        ? null
        : (json['tags'] as List)
              .map((e) => (e as String?)!)
              .toList()
              .cast<String>())!,
    steps: (json['steps'] == null
        ? null
        : (json['steps'] as List)
              .map(
                (e) =>
                    (e == null ? null : Map<String, dynamic>.from(e as Map))!,
              )
              .toList()
              .cast<Map<String, dynamic>>())!,
    starCount: (_int(json['star_count']))!,
    forkCount: (_int(json['fork_count']))!,
    createdAt: (_date(json['created_at']))!,
    ingredients: (json['ingredients'] == null
        ? null
        : (json['ingredients'] as List)
              .map(
                (e) => (e == null
                    ? null
                    : IngredientResponse.fromJson(e as Map<String, dynamic>))!,
              )
              .toList()
              .cast<IngredientResponse>())!,
  );
}

/// `RecipeUpdate` from the API schema.
class RecipeUpdate {
  final String? name;
  final String? description;
  final bool? isPublic;
  final double? defaultDoughWeightG;
  final double? starterHydrationPct;
  final List<String>? tags;
  final List<Map<String, dynamic>>? steps;
  final List<IngredientInput>? ingredients;

  const RecipeUpdate({
    this.name,
    this.description,
    this.isPublic,
    this.defaultDoughWeightG,
    this.starterHydrationPct,
    this.tags,
    this.steps,
    this.ingredients,
  });

  factory RecipeUpdate.fromJson(Map<String, dynamic> json) => RecipeUpdate(
    name: json['name'] as String?,
    description: json['description'] as String?,
    isPublic: json['is_public'] as bool?,
    defaultDoughWeightG: _double(json['default_dough_weight_g']),
    starterHydrationPct: _double(json['starter_hydration_pct']),
    tags: json['tags'] == null
        ? null
        : (json['tags'] as List)
              .map((e) => (e as String?)!)
              .toList()
              .cast<String>(),
    steps: json['steps'] == null
        ? null
        : (json['steps'] as List)
              .map(
                (e) =>
                    (e == null ? null : Map<String, dynamic>.from(e as Map))!,
              )
              .toList()
              .cast<Map<String, dynamic>>(),
    ingredients: json['ingredients'] == null
        ? null
        : (json['ingredients'] as List)
              .map(
                (e) => (e == null
                    ? null
                    : IngredientInput.fromJson(e as Map<String, dynamic>))!,
              )
              .toList()
              .cast<IngredientInput>(),
  );
}

/// `RefreshRequest` from the API schema.
class RefreshRequest {
  final String refreshToken;

  const RefreshRequest({required this.refreshToken});

  factory RefreshRequest.fromJson(Map<String, dynamic> json) =>
      RefreshRequest(refreshToken: (json['refresh_token'] as String?)!);
}

/// `RefreshResponse` from the API schema.
class RefreshResponse {
  final String seasonName;
  final int usersRanked;

  const RefreshResponse({required this.seasonName, required this.usersRanked});

  factory RefreshResponse.fromJson(Map<String, dynamic> json) =>
      RefreshResponse(
        seasonName: (json['season_name'] as String?)!,
        usersRanked: (_int(json['users_ranked']))!,
      );
}

/// `RegisterRequest` from the API schema.
class RegisterRequest {
  final String email;
  final String password;
  final String handle;
  final String displayName;
  final String? timezone;

  const RegisterRequest({
    required this.email,
    required this.password,
    required this.handle,
    required this.displayName,
    this.timezone,
  });

  factory RegisterRequest.fromJson(Map<String, dynamic> json) =>
      RegisterRequest(
        email: (json['email'] as String?)!,
        password: (json['password'] as String?)!,
        handle: (json['handle'] as String?)!,
        displayName: (json['display_name'] as String?)!,
        timezone: json['timezone'] as String?,
      );
}

/// `ResendVerificationRequest` from the API schema.
class ResendVerificationRequest {
  final String email;

  const ResendVerificationRequest({required this.email});

  factory ResendVerificationRequest.fromJson(Map<String, dynamic> json) =>
      ResendVerificationRequest(email: (json['email'] as String?)!);
}

/// `ResetPasswordRequest` from the API schema.
class ResetPasswordRequest {
  final String token;
  final String newPassword;

  const ResetPasswordRequest({required this.token, required this.newPassword});

  factory ResetPasswordRequest.fromJson(Map<String, dynamic> json) =>
      ResetPasswordRequest(
        token: (json['token'] as String?)!,
        newPassword: (json['new_password'] as String?)!,
      );
}

/// `ScaledIngredientResponse` from the API schema.
class ScaledIngredientResponse {
  final String name;
  final String kind;
  final double percentage;
  final double grams;
  final MeasureDisplay? display;

  const ScaledIngredientResponse({
    required this.name,
    required this.kind,
    required this.percentage,
    required this.grams,
    this.display,
  });

  factory ScaledIngredientResponse.fromJson(Map<String, dynamic> json) =>
      ScaledIngredientResponse(
        name: (json['name'] as String?)!,
        kind: (json['kind'] as String?)!,
        percentage: (_double(json['percentage']))!,
        grams: (_double(json['grams']))!,
        display: json['display'] == null
            ? null
            : MeasureDisplay.fromJson(json['display'] as Map<String, dynamic>),
      );
}

/// `ScaledRecipeResponse` from the API schema.
class ScaledRecipeResponse {
  final double addedFlourG;
  final double totalDoughG;
  final List<ScaledIngredientResponse> ingredients;
  final double statedHydrationPct;
  final double trueHydrationPct;
  final double totalFlourG;
  final double totalWaterG;
  final double saltPct;
  final double starterPct;
  final int loafCount;
  final double loafWeightG;

  const ScaledRecipeResponse({
    required this.addedFlourG,
    required this.totalDoughG,
    required this.ingredients,
    required this.statedHydrationPct,
    required this.trueHydrationPct,
    required this.totalFlourG,
    required this.totalWaterG,
    required this.saltPct,
    required this.starterPct,
    required this.loafCount,
    required this.loafWeightG,
  });

  factory ScaledRecipeResponse.fromJson(Map<String, dynamic> json) =>
      ScaledRecipeResponse(
        addedFlourG: (_double(json['added_flour_g']))!,
        totalDoughG: (_double(json['total_dough_g']))!,
        ingredients: (json['ingredients'] == null
            ? null
            : (json['ingredients'] as List)
                  .map(
                    (e) => (e == null
                        ? null
                        : ScaledIngredientResponse.fromJson(
                            e as Map<String, dynamic>,
                          ))!,
                  )
                  .toList()
                  .cast<ScaledIngredientResponse>())!,
        statedHydrationPct: (_double(json['stated_hydration_pct']))!,
        trueHydrationPct: (_double(json['true_hydration_pct']))!,
        totalFlourG: (_double(json['total_flour_g']))!,
        totalWaterG: (_double(json['total_water_g']))!,
        saltPct: (_double(json['salt_pct']))!,
        starterPct: (_double(json['starter_pct']))!,
        loafCount: (_int(json['loaf_count']))!,
        loafWeightG: (_double(json['loaf_weight_g']))!,
      );
}

/// `ScheduleItem` from the API schema.
class ScheduleItem {
  final String starterId;
  final String name;
  final String state;
  final String status;
  final int feedIntervalHours;
  final DateTime? lastFedAt;
  final DateTime? nextDueAt;
  final double? hoursUntilDue;

  const ScheduleItem({
    required this.starterId,
    required this.name,
    required this.state,
    required this.status,
    required this.feedIntervalHours,
    this.lastFedAt,
    this.nextDueAt,
    this.hoursUntilDue,
  });

  factory ScheduleItem.fromJson(Map<String, dynamic> json) => ScheduleItem(
    starterId: (json['starter_id'] as String?)!,
    name: (json['name'] as String?)!,
    state: (json['state'] as String?)!,
    status: (json['status'] as String?)!,
    feedIntervalHours: (_int(json['feed_interval_hours']))!,
    lastFedAt: _date(json['last_fed_at']),
    nextDueAt: _date(json['next_due_at']),
    hoursUntilDue: _double(json['hours_until_due']),
  );
}

/// `ScheduledResponse` from the API schema.
class ScheduledResponse {
  final String id;
  final String event;
  final DateTime dueAt;
  final String status;
  final int attempts;
  final String dedupeKey;
  final String? lastError;

  const ScheduledResponse({
    required this.id,
    required this.event,
    required this.dueAt,
    required this.status,
    required this.attempts,
    required this.dedupeKey,
    this.lastError,
  });

  factory ScheduledResponse.fromJson(Map<String, dynamic> json) =>
      ScheduledResponse(
        id: (json['id'] as String?)!,
        event: (json['event'] as String?)!,
        dueAt: (_date(json['due_at']))!,
        status: (json['status'] as String?)!,
        attempts: (_int(json['attempts']))!,
        dedupeKey: (json['dedupe_key'] as String?)!,
        lastError: json['last_error'] as String?,
      );
}

/// `SettingsResponse` from the API schema.
class SettingsResponse {
  final int? quietHoursStart;
  final int? quietHoursEnd;
  final Map<String, dynamic> preferences;
  final bool digestEnabled;
  final int digestWeekday;
  final int digestHour;
  final String timezone;
  final bool webpushAvailable;

  const SettingsResponse({
    this.quietHoursStart,
    this.quietHoursEnd,
    required this.preferences,
    required this.digestEnabled,
    required this.digestWeekday,
    required this.digestHour,
    required this.timezone,
    required this.webpushAvailable,
  });

  factory SettingsResponse.fromJson(Map<String, dynamic> json) =>
      SettingsResponse(
        quietHoursStart: _int(json['quiet_hours_start']),
        quietHoursEnd: _int(json['quiet_hours_end']),
        preferences: (json['preferences'] == null
            ? null
            : Map<String, dynamic>.from(json['preferences'] as Map))!,
        digestEnabled: (json['digest_enabled'] as bool?)!,
        digestWeekday: (_int(json['digest_weekday']))!,
        digestHour: (_int(json['digest_hour']))!,
        timezone: (json['timezone'] as String?)!,
        webpushAvailable: (json['webpush_available'] as bool?)!,
      );
}

/// `SettingsUpdate` from the API schema.
class SettingsUpdate {
  final int? quietHoursStart;
  final int? quietHoursEnd;
  final Map<String, dynamic>? preferences;
  final bool? digestEnabled;
  final int? digestWeekday;
  final int? digestHour;

  const SettingsUpdate({
    this.quietHoursStart,
    this.quietHoursEnd,
    this.preferences,
    this.digestEnabled,
    this.digestWeekday,
    this.digestHour,
  });

  factory SettingsUpdate.fromJson(Map<String, dynamic> json) => SettingsUpdate(
    quietHoursStart: _int(json['quiet_hours_start']),
    quietHoursEnd: _int(json['quiet_hours_end']),
    preferences: json['preferences'] == null
        ? null
        : Map<String, dynamic>.from(json['preferences'] as Map),
    digestEnabled: json['digest_enabled'] as bool?,
    digestWeekday: _int(json['digest_weekday']),
    digestHour: _int(json['digest_hour']),
  );
}

/// `StarterCreate` from the API schema.
class StarterCreate {
  final String name;
  final String? flourType;
  final DateTime? birthday;
  final String? notes;
  final int? ratioStarter;
  final int? ratioFlour;
  final int? ratioWater;
  final int? feedIntervalHours;
  final String? state;

  const StarterCreate({
    required this.name,
    this.flourType,
    this.birthday,
    this.notes,
    this.ratioStarter,
    this.ratioFlour,
    this.ratioWater,
    this.feedIntervalHours,
    this.state,
  });

  factory StarterCreate.fromJson(Map<String, dynamic> json) => StarterCreate(
    name: (json['name'] as String?)!,
    flourType: json['flour_type'] as String?,
    birthday: _date(json['birthday']),
    notes: json['notes'] as String?,
    ratioStarter: _int(json['ratio_starter']),
    ratioFlour: _int(json['ratio_flour']),
    ratioWater: _int(json['ratio_water']),
    feedIntervalHours: _int(json['feed_interval_hours']),
    state: json['state'] as String?,
  );
}

/// List view carries just enough schedule context to render a dashboard.
class StarterListItem {
  final String id;
  final String name;
  final String flourType;
  final DateTime? birthday;
  final String? notes;
  final String? avatarObjectKey;
  final int ratioStarter;
  final int ratioFlour;
  final int ratioWater;
  final double hydrationPct;
  final int feedIntervalHours;
  final String state;
  final DateTime createdAt;
  final String status;
  final DateTime? lastFedAt;
  final DateTime? nextDueAt;
  final double? hoursUntilDue;

  const StarterListItem({
    required this.id,
    required this.name,
    required this.flourType,
    this.birthday,
    this.notes,
    this.avatarObjectKey,
    required this.ratioStarter,
    required this.ratioFlour,
    required this.ratioWater,
    required this.hydrationPct,
    required this.feedIntervalHours,
    required this.state,
    required this.createdAt,
    required this.status,
    this.lastFedAt,
    this.nextDueAt,
    this.hoursUntilDue,
  });

  factory StarterListItem.fromJson(Map<String, dynamic> json) =>
      StarterListItem(
        id: (json['id'] as String?)!,
        name: (json['name'] as String?)!,
        flourType: (json['flour_type'] as String?)!,
        birthday: _date(json['birthday']),
        notes: json['notes'] as String?,
        avatarObjectKey: json['avatar_object_key'] as String?,
        ratioStarter: (_int(json['ratio_starter']))!,
        ratioFlour: (_int(json['ratio_flour']))!,
        ratioWater: (_int(json['ratio_water']))!,
        hydrationPct: (_double(json['hydration_pct']))!,
        feedIntervalHours: (_int(json['feed_interval_hours']))!,
        state: (json['state'] as String?)!,
        createdAt: (_date(json['created_at']))!,
        status: (json['status'] as String?)!,
        lastFedAt: _date(json['last_fed_at']),
        nextDueAt: _date(json['next_due_at']),
        hoursUntilDue: _double(json['hours_until_due']),
      );
}

/// `StarterResponse` from the API schema.
class StarterResponse {
  final String id;
  final String name;
  final String flourType;
  final DateTime? birthday;
  final String? notes;
  final String? avatarObjectKey;
  final int ratioStarter;
  final int ratioFlour;
  final int ratioWater;
  final double hydrationPct;
  final int feedIntervalHours;
  final String state;
  final DateTime createdAt;

  const StarterResponse({
    required this.id,
    required this.name,
    required this.flourType,
    this.birthday,
    this.notes,
    this.avatarObjectKey,
    required this.ratioStarter,
    required this.ratioFlour,
    required this.ratioWater,
    required this.hydrationPct,
    required this.feedIntervalHours,
    required this.state,
    required this.createdAt,
  });

  factory StarterResponse.fromJson(Map<String, dynamic> json) =>
      StarterResponse(
        id: (json['id'] as String?)!,
        name: (json['name'] as String?)!,
        flourType: (json['flour_type'] as String?)!,
        birthday: _date(json['birthday']),
        notes: json['notes'] as String?,
        avatarObjectKey: json['avatar_object_key'] as String?,
        ratioStarter: (_int(json['ratio_starter']))!,
        ratioFlour: (_int(json['ratio_flour']))!,
        ratioWater: (_int(json['ratio_water']))!,
        hydrationPct: (_double(json['hydration_pct']))!,
        feedIntervalHours: (_int(json['feed_interval_hours']))!,
        state: (json['state'] as String?)!,
        createdAt: (_date(json['created_at']))!,
      );
}

/// `StarterUpdate` from the API schema.
class StarterUpdate {
  final String? name;
  final String? flourType;
  final DateTime? birthday;
  final String? notes;
  final int? ratioStarter;
  final int? ratioFlour;
  final int? ratioWater;
  final int? feedIntervalHours;
  final String? state;

  const StarterUpdate({
    this.name,
    this.flourType,
    this.birthday,
    this.notes,
    this.ratioStarter,
    this.ratioFlour,
    this.ratioWater,
    this.feedIntervalHours,
    this.state,
  });

  factory StarterUpdate.fromJson(Map<String, dynamic> json) => StarterUpdate(
    name: json['name'] as String?,
    flourType: json['flour_type'] as String?,
    birthday: _date(json['birthday']),
    notes: json['notes'] as String?,
    ratioStarter: _int(json['ratio_starter']),
    ratioFlour: _int(json['ratio_flour']),
    ratioWater: _int(json['ratio_water']),
    feedIntervalHours: _int(json['feed_interval_hours']),
    state: json['state'] as String?,
  );
}

/// `StreakResponse` from the API schema.
class StreakResponse {
  final String starterId;
  final int current;
  final int longest;
  final int totalFeedings;
  final DateTime? lastFedAt;
  final DateTime? nextDueAt;
  final DateTime? deadlineAt;
  final bool isAlive;

  const StreakResponse({
    required this.starterId,
    required this.current,
    required this.longest,
    required this.totalFeedings,
    this.lastFedAt,
    this.nextDueAt,
    this.deadlineAt,
    required this.isAlive,
  });

  factory StreakResponse.fromJson(Map<String, dynamic> json) => StreakResponse(
    starterId: (json['starter_id'] as String?)!,
    current: (_int(json['current']))!,
    longest: (_int(json['longest']))!,
    totalFeedings: (_int(json['total_feedings']))!,
    lastFedAt: _date(json['last_fed_at']),
    nextDueAt: _date(json['next_due_at']),
    deadlineAt: _date(json['deadline_at']),
    isAlive: (json['is_alive'] as bool?)!,
  );
}

/// `SuggestFeedRequest` from the API schema.
class SuggestFeedRequest {
  final double? starterG;
  final double? totalG;

  const SuggestFeedRequest({this.starterG, this.totalG});

  factory SuggestFeedRequest.fromJson(Map<String, dynamic> json) =>
      SuggestFeedRequest(
        starterG: _double(json['starter_g']),
        totalG: _double(json['total_g']),
      );
}

/// `SuggestedFeedResponse` from the API schema.
class SuggestedFeedResponse {
  final double starterG;
  final double flourG;
  final double waterG;
  final double totalG;
  final double hydrationPct;
  final MeasureDisplay? starterDisplay;
  final MeasureDisplay? flourDisplay;
  final MeasureDisplay? waterDisplay;

  const SuggestedFeedResponse({
    required this.starterG,
    required this.flourG,
    required this.waterG,
    required this.totalG,
    required this.hydrationPct,
    this.starterDisplay,
    this.flourDisplay,
    this.waterDisplay,
  });

  factory SuggestedFeedResponse.fromJson(Map<String, dynamic> json) =>
      SuggestedFeedResponse(
        starterG: (_double(json['starter_g']))!,
        flourG: (_double(json['flour_g']))!,
        waterG: (_double(json['water_g']))!,
        totalG: (_double(json['total_g']))!,
        hydrationPct: (_double(json['hydration_pct']))!,
        starterDisplay: json['starter_display'] == null
            ? null
            : MeasureDisplay.fromJson(
                json['starter_display'] as Map<String, dynamic>,
              ),
        flourDisplay: json['flour_display'] == null
            ? null
            : MeasureDisplay.fromJson(
                json['flour_display'] as Map<String, dynamic>,
              ),
        waterDisplay: json['water_display'] == null
            ? null
            : MeasureDisplay.fromJson(
                json['water_display'] as Map<String, dynamic>,
              ),
      );
}

/// `SuspendRequest` from the API schema.
class SuspendRequest {
  final String reason;

  const SuspendRequest({required this.reason});

  factory SuspendRequest.fromJson(Map<String, dynamic> json) =>
      SuspendRequest(reason: (json['reason'] as String?)!);
}

/// `TestNotificationRequest` from the API schema.
class TestNotificationRequest {
  final String? kind;

  const TestNotificationRequest({this.kind});

  factory TestNotificationRequest.fromJson(Map<String, dynamic> json) =>
      TestNotificationRequest(kind: json['kind'] as String?);
}

/// `TierResponse` from the API schema.
class TierResponse {
  final String tier;
  final String icon;
  final int lifetimeXp;
  final int seasonXp;
  final String seasonName;
  final String? nextTier;
  final int? xpToNext;
  final double progressPct;
  final int achievementsEarned;
  final int achievementsTotal;

  const TierResponse({
    required this.tier,
    required this.icon,
    required this.lifetimeXp,
    required this.seasonXp,
    required this.seasonName,
    this.nextTier,
    this.xpToNext,
    required this.progressPct,
    required this.achievementsEarned,
    required this.achievementsTotal,
  });

  factory TierResponse.fromJson(Map<String, dynamic> json) => TierResponse(
    tier: (json['tier'] as String?)!,
    icon: (json['icon'] as String?)!,
    lifetimeXp: (_int(json['lifetime_xp']))!,
    seasonXp: (_int(json['season_xp']))!,
    seasonName: (json['season_name'] as String?)!,
    nextTier: json['next_tier'] as String?,
    xpToNext: _int(json['xp_to_next']),
    progressPct: (_double(json['progress_pct']))!,
    achievementsEarned: (_int(json['achievements_earned']))!,
    achievementsTotal: (_int(json['achievements_total']))!,
  );
}

/// `TokenResponse` from the API schema.
class TokenResponse {
  final String accessToken;
  final String refreshToken;
  final String? tokenType;
  final int expiresIn;

  const TokenResponse({
    required this.accessToken,
    required this.refreshToken,
    this.tokenType,
    required this.expiresIn,
  });

  factory TokenResponse.fromJson(Map<String, dynamic> json) => TokenResponse(
    accessToken: (json['access_token'] as String?)!,
    refreshToken: (json['refresh_token'] as String?)!,
    tokenType: json['token_type'] as String?,
    expiresIn: (_int(json['expires_in']))!,
  );
}

/// `TransactionCreate` from the API schema.
class TransactionCreate {
  final String kind;
  final double? quantityG;
  final double? quantity;
  final String? unit;
  final double? unitCostPerKg;
  final DateTime? occurredAt;
  final String? note;
  final bool? decrease;

  const TransactionCreate({
    required this.kind,
    this.quantityG,
    this.quantity,
    this.unit,
    this.unitCostPerKg,
    this.occurredAt,
    this.note,
    this.decrease,
  });

  factory TransactionCreate.fromJson(Map<String, dynamic> json) =>
      TransactionCreate(
        kind: (json['kind'] as String?)!,
        quantityG: _double(json['quantity_g']),
        quantity: _double(json['quantity']),
        unit: json['unit'] as String?,
        unitCostPerKg: _double(json['unit_cost_per_kg']),
        occurredAt: _date(json['occurred_at']),
        note: json['note'] as String?,
        decrease: json['decrease'] as bool?,
      );
}

/// `TransactionResponse` from the API schema.
class TransactionResponse {
  final String id;
  final String itemId;
  final String kind;
  final double deltaG;
  final double? unitCostPerKg;
  final DateTime occurredAt;
  final String? note;
  final String? bakeId;

  const TransactionResponse({
    required this.id,
    required this.itemId,
    required this.kind,
    required this.deltaG,
    this.unitCostPerKg,
    required this.occurredAt,
    this.note,
    this.bakeId,
  });

  factory TransactionResponse.fromJson(Map<String, dynamic> json) =>
      TransactionResponse(
        id: (json['id'] as String?)!,
        itemId: (json['item_id'] as String?)!,
        kind: (json['kind'] as String?)!,
        deltaG: (_double(json['delta_g']))!,
        unitCostPerKg: _double(json['unit_cost_per_kg']),
        occurredAt: (_date(json['occurred_at']))!,
        note: json['note'] as String?,
        bakeId: json['bake_id'] as String?,
      );
}

/// `UnitCatalogueResponse` from the API schema.
class UnitCatalogueResponse {
  final List<UnitInfo> units;
  final String note;

  const UnitCatalogueResponse({required this.units, required this.note});

  factory UnitCatalogueResponse.fromJson(Map<String, dynamic> json) =>
      UnitCatalogueResponse(
        units: (json['units'] == null
            ? null
            : (json['units'] as List)
                  .map(
                    (e) => (e == null
                        ? null
                        : UnitInfo.fromJson(e as Map<String, dynamic>))!,
                  )
                  .toList()
                  .cast<UnitInfo>())!,
        note: (json['note'] as String?)!,
      );
}

/// One unit and its exact relationship to the base of its family.
class UnitInfo {
  final String unit;
  final String label;
  final String family;
  final double? grams;
  final double? millilitres;

  const UnitInfo({
    required this.unit,
    required this.label,
    required this.family,
    this.grams,
    this.millilitres,
  });

  factory UnitInfo.fromJson(Map<String, dynamic> json) => UnitInfo(
    unit: (json['unit'] as String?)!,
    label: (json['label'] as String?)!,
    family: (json['family'] as String?)!,
    grams: _double(json['grams']),
    millilitres: _double(json['millilitres']),
  );
}

/// `VerifyEmailRequest` from the API schema.
class VerifyEmailRequest {
  final String token;

  const VerifyEmailRequest({required this.token});

  factory VerifyEmailRequest.fromJson(Map<String, dynamic> json) =>
      VerifyEmailRequest(token: (json['token'] as String?)!);
}

/// The shape a browser's PushSubscription serialises to.
class WebPushSubscription {
  final String endpoint;
  final Map<String, dynamic> keys;
  final String? label;

  const WebPushSubscription({
    required this.endpoint,
    required this.keys,
    this.label,
  });

  factory WebPushSubscription.fromJson(Map<String, dynamic> json) =>
      WebPushSubscription(
        endpoint: (json['endpoint'] as String?)!,
        keys: (json['keys'] == null
            ? null
            : Map<String, dynamic>.from(json['keys'] as Map))!,
        label: json['label'] as String?,
      );
}

/// `XPEventResponse` from the API schema.
class XPEventResponse {
  final String ruleCode;
  final String sourceType;
  final int amount;
  final DateTime createdAt;

  const XPEventResponse({
    required this.ruleCode,
    required this.sourceType,
    required this.amount,
    required this.createdAt,
  });

  factory XPEventResponse.fromJson(Map<String, dynamic> json) =>
      XPEventResponse(
        ruleCode: (json['rule_code'] as String?)!,
        sourceType: (json['source_type'] as String?)!,
        amount: (_int(json['amount']))!,
        createdAt: (_date(json['created_at']))!,
      );
}
