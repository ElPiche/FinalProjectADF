package com.da.extractor.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Transformer - Componente responsable de transformar y procesar los datos extraídos.
 *
 * Funcionalidades principales:
 * - Agrupación de datos por campos específicos
 * - Filtrado y limpieza de datos
 * - Normalización de campos
 * - Agregaciones y cálculos
 * - Generación de JSON limpio para carga
 */
@Slf4j
@Service
public class DataTransformer {

    /**
     * Transforma los datos extraídos aplicando agrupaciones, filtros y normalizaciones.
     *
     * @param rawData Datos extraídos de Elasticsearch
     * @param transformationType Tipo de transformación a aplicar
     * @return Lista de documentos transformados listos para cargar
     */
    public List<Map<String, Object>> transformData(List<Map<String, Object>> rawData, String transformationType) {
        log.info("Transformando {} registros usando tipo: {}", rawData.size(), transformationType);

        if (rawData == null || rawData.isEmpty()) {
            log.warn("No hay datos para transformar");
            return new ArrayList<>();
        }

        try {
            List<Map<String, Object>> transformedData = switch (transformationType.toLowerCase()) {
                case "error_aggregation" -> transformErrorAggregation(rawData);
                case "performance_metrics" -> transformPerformanceMetrics(rawData);
                case "user_activity" -> transformUserActivity(rawData);
                case "system_health" -> transformSystemHealth(rawData);
                default -> transformDefault(rawData);
            };

            log.info("Transformación completada: {} registros procesados -> {} registros resultantes",
                    rawData.size(), transformedData.size());

            return transformedData;

        } catch (Exception e) {
            log.error("Error durante la transformación de datos: {}", e.getMessage(), e);
            throw new RuntimeException("Falló la transformación de datos", e);
        }
    }

    /**
     * Transformación para agregación de errores.
     * Agrupa errores por código y cuenta ocurrencias.
     */
    private List<Map<String, Object>> transformErrorAggregation(List<Map<String, Object>> rawData) {
        log.debug("Aplicando transformación de agregación de errores");

        Map<String, Map<String, Object>> errorGroups = rawData.stream()
            .filter(this::isErrorLog)
            .collect(Collectors.groupingBy(
                this::getErrorCode,
                Collectors.collectingAndThen(
                    Collectors.toList(),
                    this::createErrorAggregation
                )
            ));

        return new ArrayList<>(errorGroups.values());
    }

    /**
     * Transformación para métricas de rendimiento.
     * Calcula estadísticas de tiempo de respuesta y throughput.
     */
    private List<Map<String, Object>> transformPerformanceMetrics(List<Map<String, Object>> rawData) {
        log.debug("Aplicando transformación de métricas de rendimiento");

        // Agrupar por endpoint/servicio
        Map<String, List<Map<String, Object>>> endpointGroups = rawData.stream()
            .filter(this::isPerformanceLog)
            .collect(Collectors.groupingBy(this::getEndpoint));

        return endpointGroups.entrySet().stream()
            .map(entry -> createPerformanceMetric(entry.getKey(), entry.getValue()))
            .collect(Collectors.toList());
    }

    /**
     * Transformación para actividad de usuarios.
     * Agrupa acciones por usuario y calcula métricas de uso.
     */
    private List<Map<String, Object>> transformUserActivity(List<Map<String, Object>> rawData) {
        log.debug("Aplicando transformación de actividad de usuarios");

        Map<String, List<Map<String, Object>>> userGroups = rawData.stream()
            .filter(this::hasUserInfo)
            .collect(Collectors.groupingBy(this::getUserId));

        return userGroups.entrySet().stream()
            .map(entry -> createUserActivitySummary(entry.getKey(), entry.getValue()))
            .collect(Collectors.toList());
    }

    /**
     * Transformación para salud del sistema.
     * Calcula métricas de disponibilidad y estado de servicios.
     */
    private List<Map<String, Object>> transformSystemHealth(List<Map<String, Object>> rawData) {
        log.debug("Aplicando transformación de salud del sistema");

        Map<String, List<Map<String, Object>>> serviceGroups = rawData.stream()
            .collect(Collectors.groupingBy(this::getServiceName));

        return serviceGroups.entrySet().stream()
            .map(entry -> createHealthMetric(entry.getKey(), entry.getValue()))
            .collect(Collectors.toList());
    }

    /**
     * Transformación por defecto.
     * Limpia y normaliza campos básicos.
     */
    private List<Map<String, Object>> transformDefault(List<Map<String, Object>> rawData) {
        log.debug("Aplicando transformación por defecto");

        return rawData.stream()
            .map(this::cleanAndNormalizeDocument)
            .collect(Collectors.toList());
    }

    // Métodos auxiliares para extraer información de documentos

    private boolean isErrorLog(Map<String, Object> document) {
        Object level = document.get("level");
        Object status = document.get("status");
        return "ERROR".equals(level) || "FATAL".equals(level) ||
               (status instanceof Number && ((Number) status).intValue() >= 400);
    }

    private boolean isPerformanceLog(Map<String, Object> document) {
        return document.containsKey("response_time") || document.containsKey("duration");
    }

    private boolean hasUserInfo(Map<String, Object> document) {
        return document.containsKey("user_id") || document.containsKey("username");
    }

    private String getErrorCode(Map<String, Object> document) {
        Object errorCode = document.get("error_code");
        Object status = document.get("status");
        if (errorCode != null) return errorCode.toString();
        if (status != null) return status.toString();
        return "UNKNOWN";
    }

    private String getEndpoint(Map<String, Object> document) {
        Object endpoint = document.get("endpoint");
        Object path = document.get("path");
        Object url = document.get("url");
        if (endpoint != null) return endpoint.toString();
        if (path != null) return path.toString();
        if (url != null) return url.toString();
        return "unknown";
    }

    private String getUserId(Map<String, Object> document) {
        Object userId = document.get("user_id");
        Object username = document.get("username");
        if (userId != null) return userId.toString();
        if (username != null) return username.toString();
        return "anonymous";
    }

    private String getServiceName(Map<String, Object> document) {
        Object service = document.get("service");
        Object serviceName = document.get("service_name");
        if (service != null) return service.toString();
        if (serviceName != null) return serviceName.toString();
        return "unknown";
    }

    // Métodos para crear agregaciones

    private Map<String, Object> createErrorAggregation(List<Map<String, Object>> errors) {
        Map<String, Object> aggregation = new HashMap<>();
        aggregation.put("error_code", getErrorCode(errors.get(0)));
        aggregation.put("count", errors.size());
        aggregation.put("first_occurrence", getTimestamp(errors.get(0)));
        aggregation.put("last_occurrence", getTimestamp(errors.get(errors.size() - 1)));
        aggregation.put("processed_at", LocalDateTime.now());

        // Extraer mensajes únicos
        Set<String> uniqueMessages = errors.stream()
            .map(e -> e.get("message"))
            .filter(Objects::nonNull)
            .map(Object::toString)
            .collect(Collectors.toSet());
        aggregation.put("unique_messages", uniqueMessages.size());

        return aggregation;
    }

    private Map<String, Object> createPerformanceMetric(String endpoint, List<Map<String, Object>> logs) {
        List<Double> responseTimes = logs.stream()
            .map(log -> getResponseTime(log))
            .filter(Objects::nonNull)
            .collect(Collectors.toList());

        Map<String, Object> metric = new HashMap<>();
        metric.put("endpoint", endpoint);
        metric.put("request_count", logs.size());
        metric.put("avg_response_time", responseTimes.stream().mapToDouble(Double::doubleValue).average().orElse(0.0));
        metric.put("min_response_time", responseTimes.stream().mapToDouble(Double::doubleValue).min().orElse(0.0));
        metric.put("max_response_time", responseTimes.stream().mapToDouble(Double::doubleValue).max().orElse(0.0));
        metric.put("processed_at", LocalDateTime.now());

        return metric;
    }

    private Map<String, Object> createUserActivitySummary(String userId, List<Map<String, Object>> activities) {
        Map<String, Object> summary = new HashMap<>();
        summary.put("user_id", userId);
        summary.put("activity_count", activities.size());
        summary.put("unique_actions", activities.stream()
            .map(a -> a.get("action"))
            .filter(Objects::nonNull)
            .map(Object::toString)
            .collect(Collectors.toSet()).size());
        summary.put("processed_at", LocalDateTime.now());

        return summary;
    }

    private Map<String, Object> createHealthMetric(String serviceName, List<Map<String, Object>> logs) {
        long errorCount = logs.stream()
            .filter(this::isErrorLog)
            .count();

        Map<String, Object> health = new HashMap<>();
        health.put("service_name", serviceName);
        health.put("total_logs", logs.size());
        health.put("error_count", errorCount);
        health.put("success_rate", logs.size() > 0 ? (double)(logs.size() - errorCount) / logs.size() : 0.0);
        health.put("processed_at", LocalDateTime.now());

        return health;
    }

    private Map<String, Object> cleanAndNormalizeDocument(Map<String, Object> document) {
        Map<String, Object> cleaned = new HashMap<>(document);
        cleaned.put("processed_at", LocalDateTime.now());

        // Normalizar timestamp
        Object timestamp = document.get("@timestamp");
        if (timestamp != null) {
            cleaned.put("timestamp", timestamp);
        }

        return cleaned;
    }

    private Object getTimestamp(Map<String, Object> document) {
        Object timestamp = document.get("@timestamp");
        return timestamp != null ? timestamp : document.get("timestamp");
    }

    private Double getResponseTime(Map<String, Object> document) {
        Object responseTime = document.get("response_time");
        Object duration = document.get("duration");

        if (responseTime instanceof Number) {
            return ((Number) responseTime).doubleValue();
        }
        if (duration instanceof Number) {
            return ((Number) duration).doubleValue();
        }
        return null;
    }
}
