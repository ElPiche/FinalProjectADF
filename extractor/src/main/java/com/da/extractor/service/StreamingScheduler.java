package com.da.extractor.service;

import com.da.extractor.model.EtlConfiguration;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * StreamingScheduler - Componente responsable de ejecutar jobs ETL en modo streaming.
 *
 * Funcionalidades principales:
 * - Registro de jobs para ejecución periódica
 * - Ejecución automática basada en frecuencia configurada
 * - Procesamiento de ventanas de tiempo recientes (ej: última hora)
 * - Prevención de ejecuciones simultáneas del mismo job
 * - Monitoreo de estado de jobs streaming
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class StreamingScheduler {

    private final ElasticsearchExtractor extractor;
    private final DataTransformer transformer;
    private final DataLoader loader;

    // Mapa para almacenar configuraciones de jobs streaming registrados
    private final Map<String, EtlConfiguration> registeredJobs = new ConcurrentHashMap<>();

    // Mapa para rastrear jobs en ejecución (prevenir duplicados)
    private final Map<String, Boolean> jobsInExecution = new ConcurrentHashMap<>();

    // Mapa para rastrear última ejecución de cada job
    private final Map<String, LocalDateTime> lastExecutionTime = new ConcurrentHashMap<>();

    /**
     * Registra un job de streaming para ejecución periódica.
     *
     * @param config Configuración del job ETL streaming
     */
    public void registerJob(EtlConfiguration config) {
        if (!isValidStreamingConfiguration(config)) {
            log.warn("Configuración streaming inválida para job: {}", config.getJobName());
            return;
        }

        registeredJobs.put(config.getJobName(), config);
        jobsInExecution.put(config.getJobName(), false);

        log.info("Job streaming registrado: {} (frecuencia: {} minutos)",
                config.getJobName(), config.getFrequencyMinutes());
    }

    /**
     * Método programado que ejecuta jobs streaming según su frecuencia.
     * Se ejecuta cada minuto para verificar qué jobs deben ejecutarse.
     */
    @Scheduled(fixedRate = 60000) // Cada 60 segundos
    public void executeScheduledJobs() {
        LocalDateTime now = LocalDateTime.now();

        for (EtlConfiguration config : registeredJobs.values()) {
            try {
                if (shouldExecuteJob(config, now)) {
                    executeStreamingJob(config);
                }
            } catch (Exception e) {
                log.error("Error verificando ejecución para job {}: {}",
                        config.getJobName(), e.getMessage(), e);
            }
        }
    }

    /**
     * Determina si un job debe ejecutarse basado en su frecuencia y última ejecución.
     */
    private boolean shouldExecuteJob(EtlConfiguration config, LocalDateTime now) {
        String jobName = config.getJobName();

        // Verificar si el job ya está en ejecución
        if (Boolean.TRUE.equals(jobsInExecution.get(jobName))) {
            log.debug("Job {} ya está en ejecución, saltando", jobName);
            return false;
        }

        // Obtener última ejecución
        LocalDateTime lastExecution = lastExecutionTime.get(jobName);

        // Si nunca se ha ejecutado, ejecutar ahora
        if (lastExecution == null) {
            log.debug("Job {} nunca se ha ejecutado, programando ejecución", jobName);
            return true;
        }

        // Calcular tiempo transcurrido desde última ejecución
        long minutesSinceLastExecution = java.time.Duration.between(lastExecution, now).toMinutes();

        // Verificar si ha pasado suficiente tiempo según la frecuencia configurada
        if (minutesSinceLastExecution >= config.getFrequencyMinutes()) {
            log.debug("Job {} listo para ejecutar (últimos {} min >= {} min frecuencia)",
                    jobName, minutesSinceLastExecution, config.getFrequencyMinutes());
            return true;
        }

        return false;
    }

    /**
     * Ejecuta un job ETL en modo streaming.
     */
    private void executeStreamingJob(EtlConfiguration config) {
        String jobName = config.getJobName();
        String executionId = UUID.randomUUID().toString();
        LocalDateTime startTime = LocalDateTime.now();

        // Marcar job como en ejecución
        jobsInExecution.put(jobName, true);

        log.info("=== INICIANDO JOB STREAMING: {} ===", jobName);
        log.info("Execution ID: {}", executionId);
        log.info("Frecuencia: {} minutos", config.getFrequencyMinutes());

        try {
            // FASE 1: EXTRACCIÓN
            log.debug("Extrayendo datos para job streaming: {}", jobName);
            List<Map<String, Object>> extractedData = extractor.extractData(
                config.getElasticsearchIndex(),
                config.getElasticsearchQuery(),
                config.getTimeWindow()
            );

            if (extractedData.isEmpty()) {
                log.debug("No se encontraron nuevos datos para job streaming: {}", jobName);
                return;
            }

            // FASE 2: TRANSFORMACIÓN
            String transformationType = determineTransformationType(config);
            List<Map<String, Object>> transformedData = transformer.transformData(extractedData, transformationType);

            // FASE 3: CARGA
            long loadedRecords = loader.loadData(
                transformedData,
                config.getTargetCollection(),
                executionId,
                jobName
            );

            // Actualizar tiempo de última ejecución
            lastExecutionTime.put(jobName, startTime);

            LocalDateTime endTime = LocalDateTime.now();
            long durationMs = java.time.Duration.between(startTime, endTime).toMillis();

            log.info("Job streaming completado: {} (extraídos: {}, cargados: {}, duración: {} ms)",
                    jobName, extractedData.size(), loadedRecords, durationMs);

        } catch (Exception e) {
            LocalDateTime endTime = LocalDateTime.now();
            long durationMs = java.time.Duration.between(startTime, endTime).toMillis();

            log.error("Error en job streaming {}: {} (duración: {} ms)",
                    jobName, e.getMessage(), durationMs, e);

            // Actualizar tiempo de última ejecución incluso si falló para evitar reintento inmediato
            lastExecutionTime.put(jobName, startTime);

        } finally {
            // Marcar job como no en ejecución
            jobsInExecution.put(jobName, false);
        }
    }

    /**
     * Determina el tipo de transformación basado en la configuración del job.
     */
    private String determineTransformationType(EtlConfiguration config) {
        String jobName = config.getJobName().toLowerCase();

        if (jobName.contains("error") || jobName.contains("exception")) {
            return "error_aggregation";
        } else if (jobName.contains("performance") || jobName.contains("response")) {
            return "performance_metrics";
        } else if (jobName.contains("user") || jobName.contains("activity")) {
            return "user_activity";
        } else if (jobName.contains("health") || jobName.contains("status")) {
            return "system_health";
        } else {
            return "default";
        }
    }

    /**
     * Valida que la configuración sea válida para ejecución streaming.
     */
    private boolean isValidStreamingConfiguration(EtlConfiguration config) {
        if (config == null) {
            return false;
        }

        if (!"streaming".equalsIgnoreCase(config.getMode())) {
            return false;
        }

        if (config.getFrequencyMinutes() == null || config.getFrequencyMinutes() <= 0) {
            log.warn("Frecuencia inválida para job streaming: {}", config.getJobName());
            return false;
        }

        if (config.getElasticsearchIndex() == null || config.getElasticsearchIndex().trim().isEmpty()) {
            log.warn("Índice de Elasticsearch no especificado para job: {}", config.getJobName());
            return false;
        }

        if (config.getTargetCollection() == null || config.getTargetCollection().trim().isEmpty()) {
            log.warn("Colección de destino no especificada para job: {}", config.getJobName());
            return false;
        }

        return true;
    }

    /**
     * Obtiene el estado actual de los jobs streaming registrados.
     */
    public Map<String, Object> getJobsStatus() {
        Map<String, Object> status = new ConcurrentHashMap<>();

        for (String jobName : registeredJobs.keySet()) {
            Map<String, Object> jobStatus = Map.of(
                "job_name", jobName,
                "in_execution", jobsInExecution.getOrDefault(jobName, false),
                "last_execution", lastExecutionTime.get(jobName),
                "frequency_minutes", registeredJobs.get(jobName).getFrequencyMinutes()
            );
            status.put(jobName, jobStatus);
        }

        return status;
    }

    /**
     * Desregistra un job streaming.
     */
    public void unregisterJob(String jobName) {
        registeredJobs.remove(jobName);
        jobsInExecution.remove(jobName);
        lastExecutionTime.remove(jobName);
        log.info("Job streaming desregistrado: {}", jobName);
    }
}
