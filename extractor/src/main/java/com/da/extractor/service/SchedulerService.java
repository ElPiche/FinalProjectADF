package com.da.extractor.service;

import com.da.extractor.entity.SchedulerConfig;
import com.da.extractor.entity.serie.Mode;
import com.da.extractor.entity.training.TrainConfig;
import com.da.extractor.pipeline.DataPipelineFactory;
import com.da.extractor.pipeline.PipeMetadata;
import com.da.extractor.repository.anomaly_detection.TrainingConfigRepository;
import com.da.extractor.repository.scheduler.SchedulerConfigRepository;
import jakarta.annotation.PostConstruct;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.Trigger;
import org.springframework.scheduling.support.CronTrigger;
import org.springframework.stereotype.Service;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.ScheduledFuture;

@Service
public class SchedulerService {

    private static final Logger log = LoggerFactory.getLogger(SchedulerService.class);

    private final TaskScheduler taskScheduler;

    private final Map<String, ScheduledFuture<?>> scheduledTasks = new HashMap<>();
    private final SchedulerConfigRepository schedulerConfigRepository;
    private final TrainingConfigRepository trainingConfigRepository;

    private final DataPipelineFactory dataPipelineFactory;

    private static final DateTimeFormatter ISO = DateTimeFormatter.ISO_INSTANT;

    public SchedulerService(TaskScheduler taskScheduler,
                            SchedulerConfigRepository schedulerConfigRepository,
                            TrainingConfigRepository trainingConfigRepository,
                            DataPipelineFactory dataPipelineFactory) {
        this.taskScheduler = taskScheduler;
        this.schedulerConfigRepository = schedulerConfigRepository;
        this.trainingConfigRepository = trainingConfigRepository;
        this.dataPipelineFactory = dataPipelineFactory;
    }

    @PostConstruct
    void loadScheduledTasksOnStartup(){
        log.info("========================================");
        log.info("Initializing scheduled tasks on startup...");
        log.info("========================================");

        try {
            List<SchedulerConfig> configs = schedulerConfigRepository.findAll();
            log.info("Found {} scheduler configurations in database", configs.size());

            int successCount = 0;
            int failCount = 0;

            for (SchedulerConfig config : configs) {
                try {
                    log.info("Loading scheduled task for KB ID: {} with frequency: {}",
                            config.getKbId(), config.getFrequency());
                    createStreamingTask(config);
                    successCount++;
                } catch (Exception ex) {
                    failCount++;
                    log.error("Failed to load scheduled task for KB ID: {}. Error: {}",
                            config.getKbId(), ex.getMessage(), ex);
                }
            }

            log.info("========================================");
            log.info("Scheduled tasks startup complete!");
            log.info("Successfully loaded: {}", successCount);
            log.info("Failed to load: {}", failCount);
            log.info("Total active tasks: {}", scheduledTasks.size());
            log.info("========================================");

        } catch (Exception ex) {
            log.error("========================================");
            log.error("CRITICAL ERROR loading scheduled tasks on startup: {}", ex.getMessage(), ex);
            log.error("========================================");
        }
    }

    public void createStreamingTask(SchedulerConfig config) {

        CronTrigger cronTrigger = new CronTrigger(config.getFrequency());
        Runnable task = () -> {
            try {
                // Gracefully handle missing TrainConfig instead of crashing
                var trainConfigOpt = trainingConfigRepository.findByKbId(config.getKbId());
                if (trainConfigOpt.isEmpty()) {
                    log.warn("TrainConfig not found for KB ID: {}. Skipping detection cycle.", config.getKbId());
                    return;
                }
                TrainConfig trainConfig = trainConfigOpt.get();

                if(trainConfig.isTrained()){
                    Instant to  = Instant.now();
                    Instant from = to.minusSeconds(config.getWindow());
                    String elasticQuery = config.getQuery()
                            .replace("$from", ISO.format(from))
                            .replace("$to",   ISO.format(to));

                    var pipeline = dataPipelineFactory.createPipeline(new PipeMetadata(
                        config.getKbId(),
                        config.getObservedValues(),
                        Mode.DETECTION,
                        config.getTimestampField()
                    ));
                    pipeline.process(elasticQuery);

                    config.setLastRun(Date.from(Instant.now()));
                    schedulerConfigRepository.save(config);
                    log.info("Scheduled task executed for KB ID: {} | from: {} | to: {}",
                            config.getKbId(), ISO.format(from), ISO.format(to));
                }

            } catch (Exception ex) {
                log.error("Error en scheduleStreamingTask({}): {}", config.getKbId(), ex.getMessage(), ex);
            }
        };
        // Trigger compuesto usando Instant (API moderna)
        Trigger composedTrigger = context -> {
            Instant last = context.lastScheduledExecution(); // puede ser null primera vez
            if (last == null) {
                if (config.getFrom() != null) {
                    Instant startInstant = config.getFrom().toInstant();
                    if (startInstant.isAfter(Instant.now())) {
                        return startInstant; // Primera ejecución en startAt futuro
                    }
                }
                // Ejecutar inmediatamente o según cron siguiente
                return cronTrigger.nextExecution(context);
            }
            return cronTrigger.nextExecution(context);
        };
        cancelTask(config.getKbId());
        ScheduledFuture<?> future = taskScheduler.schedule(task, composedTrigger);
        scheduledTasks.put(config.getKbId(), future);
        log.info("Scheduled task saved for KB ID: {} with frequency: {}",
                config.getKbId(), config.getFrequency());
    }

    public void cancelTask(String id) {
        ScheduledFuture<?> f = scheduledTasks.remove(id);
        if (f != null) {
            f.cancel(false);
        }
    }
}